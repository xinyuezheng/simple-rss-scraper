import logging

import feedparser
from celery import group
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from rssfeed.settings import MAXIMUM_RETRY, UPDATE_INTERVAL
from .models import Feed, Entry
from celery.exceptions import MaxRetriesExceededError

from rssfeed.celery import app

from .utils import get_published_parsed

logger = logging.getLogger(__name__)


def send_email(email, msg):
    '''
    Simulate send email
    :param email: email address
    :param msg: message
    :return: None
    '''
    logger.info(f'send email to {email}: {msg}')


def update_feed_entries(feed, parsed_dict):
    """
    Helper function to update all entries of a feed. If error occurs on one entry update, roll back the transaction
    and continue update for other entries.
    :param feed: Feed object
    :param parsed_dict: parsed dictionary returned from feedparser.parse()
    :return: True/False indicating if any error occurs during the update
    """
    update_error = False

    logger.info(f'feed {feed.feed_url} is updating')
    for entry in parsed_dict.entries:
        # continue update other entries if one or more entries update fails
        try:
            with transaction.atomic():
                Entry.get_or_create(parsed_entry=entry, feed_id=feed.id)
        except Exception as e:
            update_error = True
            logger.error(e)

    return update_error


@app.task(retry_jitter=False, max_retries=MAXIMUM_RETRY,)
def update_feed(feed_id):
    """
    Background task to update a feed and its entries. Retry if any exception occurs.
    After reaching maximum retries, mark the feed status as 'Error' and send emails to all its subscribers.
    Do not send email again if the feed was already in Error state. This is to prevent Emails sent to other
     feed subscribers if one user manually updates an error feed which fails again.
    """
    feed = Feed.objects.get(id=feed_id)
    try:    # update all entries of the feed
        d = feedparser.parse(feed.feed_url)
        if d.get('bozo'):
            raise ValidationError(f'rss feedparser failed: {d.get("bozo_exception")}')

        published_parsed = get_published_parsed(d.feed)
        if feed.published_time == published_parsed and feed.status == Feed.Status.UPDATED:
            logger.info(f"Nothing to update: {feed.title}")
            feed.last_updated = timezone.now()
            feed.save()
        else:
            update_error = update_feed_entries(feed, d)
            # indicate entry update error, trigger retry
            if update_error:
                raise APIException(f"Update entries of feed {feed.title} failed")
            else:
                feed.status = Feed.Status.UPDATED
                feed.published_time = published_parsed
                feed.last_updated = timezone.now()
                feed.save()
                logger.info(f'feed {feed.title} is updated successfully')

    except (APIException, ValidationError) as e:
        try:
            logger.warning(f'Update feed {feed.title} failed with exception: {e}')
            raise update_feed.retry(countdown=2)
        except MaxRetriesExceededError:
            logger.error(f"Maximum retries reached. Stop updating {feed.title}")
            send_email_flag = True
            if feed.status == Feed.Status.ERROR:    # If feed was already in ERROR state, do not send email again
                send_email_flag = False

            feed.status = Feed.Status.ERROR
            d = feedparser.parse(feed.feed_url)
            if not d.get('bozo'):   # if published_time can be derived
                published_parsed = get_published_parsed(d.feed)
                feed.published_time = published_parsed
            feed.last_updated = timezone.now()
            feed.save()

            if send_email_flag:
                email_list = feed.subscribers.values_list('email', flat=True)
                for email in email_list:
                    send_email(email, f"failed to update {feed.title}")


@app.task
def update_active_feeds():
    """
    Collect all active feeds which has at least one subscriber and update them periodically at background
    """
    active_feeds = Feed.objects.annotate(
        num_subscribers=Count('subscribers')).filter(
        num_subscribers__gt=0).exclude(status=Feed.Status.ERROR)
    g = group(update_feed.s(feed.id,) for feed in active_feeds)
    res = g()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(UPDATE_INTERVAL, update_active_feeds.s(), name='update active feeds')



