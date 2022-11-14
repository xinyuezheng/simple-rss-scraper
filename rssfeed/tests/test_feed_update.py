from unittest.mock import patch, MagicMock

import feedparser
import pytest
import os

from rest_framework.reverse import reverse

from rssfeed.settings import MAXIMUM_RETRY
from rssfeedapi.models import Feed
from rssfeedapi.utils import get_published_parsed


@pytest.mark.django_db
class TestFeedUpdate:
    def test_update_feed_successful(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed
        user.subscriptions.add(feed)
        num_old_entries = feed.entries.count()

        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])
        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        with patch('feedparser.parse', return_value=d):
            response = api_client.put(url)
            assert response.status_code == 200
            updated_feed = Feed.objects.get(id=feed.id)
            published_parsed = get_published_parsed(d.feed)
            assert updated_feed.published_time == published_parsed
            assert updated_feed.status == Feed.Status.UPDATED

            # Test all entries are created
            for entry in d.entries:
                assert updated_feed.entries.filter(guid=entry.id).exists()

            assert updated_feed.entries.count() == num_old_entries + len(d.entries)

    def test_after_retry_failed(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed
        user.subscriptions.add(feed)

        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])

        # Test tasks are executed 3 times. (including 2x retry)
        mock_entries_update = MagicMock(return_value=True)
        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        with patch('feedparser.parse', return_value=d):
            with patch('rssfeedapi.tasks.update_feed_entries', mock_entries_update):
                response = api_client.put(url)
                assert response.status_code == 200
                assert mock_entries_update.call_count == 1 + MAXIMUM_RETRY
                updated_feed = Feed.objects.get(id=feed.id)
                assert updated_feed.status == Feed.Status.ERROR

    def test_after_retry_successful(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed
        user.subscriptions.add(feed)

        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])

        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        # Simulate update entry: first time failed, second time is successful
        mock_feed_update = MagicMock(side_effect=[True, False])
        with patch('feedparser.parse', return_value=d):
            with patch('rssfeedapi.tasks.update_feed_entries', mock_feed_update):
                response = api_client.put(url)
                assert response.status_code == 200
                assert mock_feed_update.call_count == 2
                updated_feed = Feed.objects.get(id=feed.id)
                assert updated_feed.status == Feed.Status.UPDATED

    def test_one_entry_update_failed(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed
        user.subscriptions.add(feed)
        num_old_entries = feed.entries.count()

        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])
        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        d.entries[2]['id'] = None  # Simulate one entry update fails
        with patch('feedparser.parse', return_value=d):
            response = api_client.put(url)
            assert response.status_code == 200
            updated_feed = Feed.objects.get(id=feed.id)
            assert updated_feed.status == Feed.Status.ERROR
            # 1 less entry added due to the update error
            assert updated_feed.entries.count() == num_old_entries + len(d.entries) - 1

    def test_notify_user(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed
        user.subscriptions.add(feed)

        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])
        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml.NotExist')
        mock_send_email = MagicMock()
        with patch('feedparser.parse', return_value=d):
            with patch('rssfeedapi.tasks.send_email', mock_send_email):
                response = api_client.put(url)
                assert response.status_code == 200
                updated_feed = Feed.objects.get(id=feed.id)
                # Test the status of the feed is marked as ERROR
                assert updated_feed.status == Feed.Status.ERROR
                # Test notify user: Email is sent
                mock_send_email.assert_called_with(user.email, f"failed to update {updated_feed.title}")
                # Test Email is sent to all subscribers
                assert mock_send_email.call_count == updated_feed.subscribers.count()

    def test_do_not_spam(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed, feed is already in Error state from previous update
        user.subscriptions.add(feed)
        feed.status = Feed.Status.ERROR
        feed.save()

        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])
        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml.NotExist')
        mock_send_email = MagicMock()
        with patch('feedparser.parse', return_value=d):
            with patch('rssfeedapi.tasks.send_email', mock_send_email):
                response = api_client.put(url)
                assert response.status_code == 200
                updated_feed = Feed.objects.get(id=feed.id)
                # Test the status of the feed is marked as ERROR
                assert updated_feed.status == Feed.Status.ERROR
                # Test Don't send Email
                assert mock_send_email.call_count == 0

    def test_nothing_to_update(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed
        user.subscriptions.add(feed)

        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])

        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        publish_parsed = get_published_parsed(d.feed)
        feed.published_time = publish_parsed
        feed.save()

        mock_entry_update = MagicMock()
        with patch('feedparser.parse', return_value=d):
            with patch('rssfeedapi.tasks.update_feed_entries', mock_entry_update):
                response = api_client.put(url)
                assert response.status_code == 200
                # Test Nothing to update "update_feed_entries" is not called
                assert mock_entry_update.call_count == 0

    def test_force_update_successful(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed. feed is recently updated but in Error state, user try to update it again
        user.subscriptions.add(feed)
        feed.status = Feed.Status.ERROR

        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])

        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        publish_parsed = get_published_parsed(d.feed)
        feed.published_time = publish_parsed
        feed.save()

        with patch('feedparser.parse', return_value=d):
            response = api_client.put(url)
            assert response.status_code == 200
            updated_feed = Feed.objects.get(id=feed.id)
            published_parsed = get_published_parsed(d.feed)
            assert updated_feed.published_time == published_parsed
            assert updated_feed.status == Feed.Status.UPDATED

            # Test all entries are created
            for entry in d.entries:
                assert updated_feed.entries.filter(guid=entry.id).exists()
