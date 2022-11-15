import logging
from time import sleep

import feedparser
from celery import group
from django.db.models import Count
from rest_framework.exceptions import APIException, ValidationError
from rssfeed.settings import MAXIMUM_RETRY, UPDATE_INTERVAL
from .models import Feed
from celery.exceptions import MaxRetriesExceededError
from rssfeed.celery import app
from .utils import get_published_parsed

logger = logging.getLogger(__name__)


def send_email(email, msg):
    """
    Simulate send email
    """
    logger.info(f'send email to {email}: {msg}')


def send_admin_email(msg):
    send_email(email='admin@api.com', msg=msg)


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

        feed = Feed.objects.get(feed_url=feed_url)
        failed_entries_list = feed.update_entries(
            parsed_entries_list=d.entries, published_parsed=published_parsed)

        for i in range(MAXIMUM_RETRY):  # retry failed entries if any
            if len(failed_entries_list):
                sleep(2)  # countdown 2s and retry
                failed_entries_list = feed.update_entries(
                     parsed_entries_list=d.entries, published_parsed=published_parsed)
            else:
                break

        if len(failed_entries_list):
            failed_entries_guid = ''
            for entry_guid in failed_entries_list:
                failed_entries_guid += f'{entry_guid.get("id", "")},'
            err_msg = f"Failed to update entries {failed_entries_guid}"
            logger.error(err_msg)
            # Notify admin.
            send_admin_email(msg=err_msg)

        # Continue update the feed in the future, regardless of the results of updating entries
        feed.update_status(
            feed_status=Feed.Status.UPDATED, published_parsed=published_parsed)
    except (ValidationError, APIException) as e:
        try:
            logger.warning(f'Parse {feed_url} failed with exception: {e}')
            raise update_feed.retry(countdown=2)
        except MaxRetriesExceededError:
            logger.error(f"Maximum retries reached. Stop updating {feed_url}")
            feed = Feed.objects.get(feed_url=feed_url)
            old_status = feed.update_status(
                feed_status=Feed.Status.ERROR, published_parsed=None)

            if old_status != Feed.Status.ERROR:
                # Notify admin
                err_msg = f"failed to update {feed.title}"
                send_admin_email(msg=err_msg)

                # Also notify subscribers??
                email_list = feed.subscribers.values_list('email', flat=True)
                for email_addr in email_list:
                    send_email(email=email_addr, msg=err_msg)


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

