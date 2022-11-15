import os
from unittest.mock import patch, MagicMock

import feedparser
import pytest
from rssfeedapi.tasks import update_active_feeds
from .utils import _create_authorized_users, _create_feeds_in_db
from rssfeedapi.models import Feed
from rssfeedapi.utils import get_published_parsed


@pytest.mark.django_db
class TestFeedUpdatePeriodic:
    def test_periodic_update_successful(self, celery_app):
        # Setup in DB. user0 subscribes feed0, user1 subscribes feed1
        users, clients = _create_authorized_users(2)
        feeds = _create_feeds_in_db(2)
        users[0].subscriptions.add(feeds[0])
        users[1].subscriptions.add(feeds[1])

        d1 = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        d2 = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/tweakers.mixed.xml')
        published_parsed1 = get_published_parsed(d1.feed)
        published_parsed2 = get_published_parsed(d2.feed)
        mock_feedparser = MagicMock(side_effect=[d1, d2])
        with patch('feedparser.parse', mock_feedparser):
            # Both feed0 and feed1 will be updated
            update_active_feeds.apply()

            # Test feed0 has been updated
            updated_feed = Feed.objects.get(id=feeds[0].id)
            assert updated_feed.status == Feed.Status.UPDATED
            assert updated_feed.published_time == published_parsed1
            assert updated_feed.last_updated > feeds[0].last_updated
            # Test all entries for feed0 are created
            for entry in d1.entries:
                assert updated_feed.entries.filter(guid=entry.id).exists()

            # Test feed1 has been updated
            updated_feed = Feed.objects.get(id=feeds[1].id)
            assert updated_feed.status == Feed.Status.UPDATED
            assert updated_feed.published_time == published_parsed2
            assert updated_feed.last_updated > feeds[1].last_updated
            # Test all entries for feed1 are created
            for entry in d2.entries:
                assert updated_feed.entries.filter(guid=entry.id).exists()

    def test_periodic_update_one_fail(self, celery_app):
        # Setup in DB. user0 subscribes feed0, user1 subscribes feed1
        users, clients = _create_authorized_users(2)
        feeds = _create_feeds_in_db(2)
        valid_url = os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml'
        feeds[0].feed_url = valid_url
        feeds[0].save()
        users[0].subscriptions.add(feeds[0])
        users[1].subscriptions.add(feeds[1])

        d = feedparser.parse(valid_url)
        published_parsed = get_published_parsed(d.feed)
        # Both feed0 and feed1 will be updated
        update_active_feeds.apply()

        # Test feed0 has been updated successfully
        updated_feed = Feed.objects.get(id=feeds[0].id)
        assert updated_feed.status == Feed.Status.UPDATED
        assert updated_feed.published_time == published_parsed
        assert updated_feed.last_updated > feeds[0].last_updated
        # Test all entries are created
        for entry in d.entries:
            assert updated_feed.entries.filter(guid=entry.id).exists()

        # Test feed1 has been updated with error
        updated_feed = Feed.objects.get(id=feeds[1].id)
        assert updated_feed.status == Feed.Status.ERROR
        assert updated_feed.last_updated > feeds[1].last_updated

    def test_only_update_active_feed(self, celery_app):
        # Setup in DB. No one subscribes to feed1
        users, clients = _create_authorized_users(2)
        feeds = _create_feeds_in_db(2)
        users[0].subscriptions.add(feeds[0])

        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        with patch('feedparser.parse', return_value=d):
            update_active_feeds.apply()
            published_parsed = get_published_parsed(d.feed)
            # No one subscribes to feed1. Skip periodic updating it
            updated_feed = Feed.objects.get(id=feeds[1].id)
            assert updated_feed.published_time != published_parsed
            assert updated_feed.last_updated == feeds[1].last_updated

            # User0 subscribes to feed0. feed0 has been updated successfully
            updated_feed = Feed.objects.get(id=feeds[0].id)
            assert updated_feed.published_time == published_parsed
            assert updated_feed.last_updated > feeds[0].last_updated

    def test_stop_update_if_in_error_state(self, feed, user, celery_app):
        # Setup in DB. feed was already in Error state
        user.subscriptions.add(feed)
        feed.status = Feed.Status.ERROR
        feed.save()

        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        with patch('feedparser.parse', return_value=d):
            update_active_feeds.apply()
            published_parsed = get_published_parsed(d.feed)
            updated_feed = Feed.objects.get(id=feed.id)
            # feed was in error state. Skip periodically updating it
            assert updated_feed.published_time != published_parsed
            assert updated_feed.last_updated == feed.last_updated
            assert updated_feed.status == feed.status


