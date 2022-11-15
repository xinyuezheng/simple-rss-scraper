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


def update_feed_entries(feed_url, parsed_entries_list, published_parsed):
    """
    #TODO :
    Helper function to update all entries of a feed. If error occurs on one entry update, roll back the transaction
    and continue update for other entries.
    :param feed_url:
    :param parsed_entries_list: parsed dictionary returned from feedparser.parse()
    :return:
    """
    feed = Feed.objects.get(feed_url=feed_url)
    if feed.published_time == published_parsed and feed.status == Feed.Status.UPDATED:
        logger.info(f"Nothing to update: {feed.title}")
        parsed_entries_list.clear()
        return

    for entry in list(parsed_entries_list):  # make a new list for iteration
        # continue update other entries if one or more entries update fails
        try:
            with transaction.atomic():
                Entry.get_or_create(parsed_entry=entry, feed_id=feed.id)
                parsed_entries_list.remove(entry)
        except Exception as e:
            logger.error(e)


def process_feed_new_status(feed_url, feed_status, published_parsed):
    """
    This function updates the status of feed in the database. Use 'select_for_update' to block the
    row until the transaction is finished, to prevent other processes to change the status of the feed at the same time
    """
    feed = Feed.objects.select_for_update().get(feed_url=feed_url)
    with transaction.atomic():
        old_status = feed.status
        feed.last_updated = timezone.now()
        feed.status = feed_status
        if published_parsed:
            feed.published_time = published_parsed
        feed.save()

    if old_status == Feed.Status.UPDATED and feed_status == Feed.Status.ERROR:
        email_list = feed.subscribers.values_list('email', flat=True)
        for email_addr in email_list:
            send_email(email_addr, f"failed to update {feed.title}")


@app.task(retry_jitter=False, max_retries=MAXIMUM_RETRY,)
def update_feed(feed_url):
    """
    Background task to update a feed and its entries. Retry if any exception occurs.
    After reaching maximum retries, mark the feed status as 'Error' and send emails to all its subscribers.
    Do not send email again if the feed was already in Error state. This is to prevent Emails sent to other
     feed subscribers if one user manually updates an error feed which fails again.
    """
    try:
        d = feedparser.parse(feed_url)
        if d.get('bozo'):
            raise ValidationError(f'rss feedparser failed: {d.get("bozo_exception")}')
        published_parsed = get_published_parsed(d.feed)

        parsed_entries = d.entries
        update_feed_entries(feed_url, parsed_entries, published_parsed)

        for i in range(MAXIMUM_RETRY):  # retry failed entries if any
            if len(parsed_entries):
                update_feed_entries(feed_url, parsed_entries, published_parsed)
            else:
                break

        if len(parsed_entries):
            failed_entries_guid = ''
            for entry_guid in parsed_entries:
                failed_entries_guid += f'{entry_guid.get("id", "")},'
            logger.error(f"Failed to update entries {failed_entries_guid}")
            process_feed_new_status(feed_url, Feed.Status.ERROR, published_parsed)
        else:
            process_feed_new_status(feed_url, Feed.Status.UPDATED, published_parsed)

    except (ValidationError, APIException) as e:
        try:
            logger.warning(f'Parse {feed_url} failed with exception: {e}')
            raise update_feed.retry(countdown=2)
        except MaxRetriesExceededError:
            logger.error(f"Maximum retries reached. Stop updating {feed_url}")
            process_feed_new_status(feed_url, Feed.Status.ERROR, None)


@app.task
def update_active_feeds():
    """
    Collect all active feeds which has at least one subscriber and update them periodically at background
    """
    active_feeds = Feed.objects.annotate(
        num_subscribers=Count('subscribers')).filter(
        num_subscribers__gt=0).exclude(status=Feed.Status.ERROR)
    g = group(update_feed.s(feed.feed_url,) for feed in active_feeds)
    res = g()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(UPDATE_INTERVAL, update_active_feeds.s(), name='update active feeds')



