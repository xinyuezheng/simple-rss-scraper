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
            assert updated_feed.last_updated > feed.last_updated

            # Test all entries are created
            for entry in d.entries:
                assert updated_feed.entries.filter(guid=entry.id).exists()

            assert updated_feed.entries.count() == num_old_entries + len(d.entries)

    def test_parse_feed_failed(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed
        user.subscriptions.add(feed)

        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])
        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/NotValid.xml')
        mock_feedparser = MagicMock(return_value=d)
        mock_send_admin_email = MagicMock()
        with patch('feedparser.parse', mock_feedparser):
            with patch('rssfeedapi.tasks.send_admin_email', mock_send_admin_email):
                response = api_client.put(url)
                assert response.status_code == 200
                assert mock_feedparser.call_count == 1 + MAXIMUM_RETRY  # First time failed + Maximum Retry reached
                updated_feed = Feed.objects.get(id=feed.id)
                assert updated_feed.status == Feed.Status.ERROR
                assert updated_feed.last_updated > feed.last_updated
                # published time stays the same because it cannot be parsed
                assert updated_feed.published_time == feed.published_time

                # Test notify admin: Email is sent
                mock_send_admin_email.call_count == 1

    def test_update_entries_with_exception(self, user, api_client, feed, celery_app):
        num_old_entries = feed.entries.count()
        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        d.entries[0]['id'] = None  # Simulate one entry has error
        published_parsed = get_published_parsed(d.feed)
        with patch('feedparser.parse', return_value=d):
            faild_entreis_list = feed.update_entries(
                parsed_entries_list=d.entries, published_parsed=published_parsed)
            assert d.entries[0] in faild_entreis_list
            updated_feed = Feed.objects.get(id=feed.id)
            # 1 less entry added to DB due to the update error
            assert updated_feed.entries.count() == num_old_entries + len(d.entries) - 1

    def test_entry_update_retry_failed(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed
        user.subscriptions.add(feed)
        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])

        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        mock_entries_update = MagicMock(return_value=[d.entries[0]])
        mock_send_admin_email = MagicMock()

        with patch('feedparser.parse', return_value=d):
            with patch('rssfeedapi.models.Feed.update_entries', mock_entries_update):
                with patch('rssfeedapi.tasks.send_admin_email', mock_send_admin_email):
                    response = api_client.put(url)
                    assert response.status_code == 200
                    # Maximum Retry reached
                    assert mock_entries_update.call_count == MAXIMUM_RETRY + 1
                    updated_feed = Feed.objects.get(id=feed.id)
                    published_parsed = get_published_parsed(d.feed)
                    assert updated_feed.published_time == published_parsed
                    assert updated_feed.status == Feed.Status.UPDATED
                    assert updated_feed.last_updated > feed.last_updated

                    # Test notify admin: Email is sent
                    mock_send_admin_email.assert_called_with(msg=f"Failed to update entries {d.entries[0]['id']},")

    def test_entry_update_retry_successful(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed
        user.subscriptions.add(feed)

        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])

        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        # Simulate update entry: first time one entry with error, second time no error
        mock_feed_update = MagicMock(side_effect=[[d.entries[0]], []])
        mock_send_admin_email = MagicMock()

        with patch('feedparser.parse', return_value=d):
            with patch('rssfeedapi.models.Feed.update_entries', mock_feed_update):
                with patch('rssfeedapi.tasks.send_admin_email', mock_send_admin_email):
                    response = api_client.put(url)
                    assert response.status_code == 200
                    assert mock_feed_update.call_count == 2
                    updated_feed = Feed.objects.get(id=feed.id)
                    published_parsed = get_published_parsed(d.feed)
                    assert updated_feed.published_time == published_parsed
                    assert updated_feed.status == Feed.Status.UPDATED
                    assert updated_feed.last_updated > feed.last_updated
                    # No email is sent
                    mock_send_admin_email.call_count == 0

    def test_do_not_spam(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed, feed is already in Error state from previous update
        user.subscriptions.add(feed)
        feed.status = Feed.Status.ERROR
        feed.save()

        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])
        mock_send_admin_email = MagicMock()
        with patch('rssfeedapi.tasks.send_admin_email', mock_send_admin_email):
            response = api_client.put(url)
            assert response.status_code == 200
            # Test Don't send Email
            assert mock_send_admin_email.call_count == 0

    def test_nothing_to_update(self, user, api_client, feed, celery_app):
        # Set up in DB: user subscribe to feed
        user.subscriptions.add(feed)

        url = reverse("rssfeedapi:feed_detail",  args=[feed.id])

        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        publish_parsed = get_published_parsed(d.feed)
        feed.published_time = publish_parsed
        feed.save()

        mock_create_entry = MagicMock()
        with patch('feedparser.parse', return_value=d):
            with patch('rssfeedapi.models.Entry.get_or_create', mock_create_entry):
                response = api_client.put(url)
                assert response.status_code == 200
                # Test Nothing to update "Entry.get_or_create" is not called
                assert mock_create_entry.call_count == 0

    def test_force_update_from_error_state(self, user, api_client, feed, celery_app):
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
            assert updated_feed.last_updated > feed.last_updated

            # Test all entries are created
            for entry in d.entries:
                assert updated_feed.entries.filter(guid=entry.id).exists()
