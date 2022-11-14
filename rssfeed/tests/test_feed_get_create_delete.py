import os
from unittest.mock import patch
import feedparser
import pytest
from django.urls import reverse
from rest_framework import serializers

from rssfeedapi.models import Feed, Entry, FeedSubscription
from rssfeedapi.utils import get_published_parsed
from tests.utils import _create_feeds_in_db


@pytest.mark.django_db
class TestFeedView:
    def test_get_feed_list(self, api_client, user):
        # Set up in DB: user subscribes 2 feeds
        feeds = _create_feeds_in_db(2)
        user.subscriptions.add(feeds[0])
        user.subscriptions.add(feeds[1])

        # Test list all subscribed feeds
        url = reverse("rssfeedapi:feed_list")
        response = api_client.get(url)
        assert response.status_code == 200
        response_json = response.json()
        assert response_json.get("count") == user.subscriptions.count()

        # Test Response from FeedListSerializer
        for res in response_json.get('results'):
            subs_id = int(res['subscription_id'])
            assert FeedSubscription.objects.filter(id=subs_id).exists()
            feed_subs = FeedSubscription.objects.get(id=subs_id)
            assert res.get("feed_url") == feed_subs.feed.feed_url
            assert feed_subs.user.username == user.username
            assert res.get("subscribed_time") == \
                   serializers.DateTimeField().to_representation(feed_subs.subscribed_time)
            feed_link = res.get('feed')
            feed_id = feed_link.rstrip('/').split('/')[-1]  # eg: 'http://testserver/feed/1/'
            assert int(feed_id) == feed_subs.feed.id

    def test_follow_a_feed(self, user, api_client, feed):
        # Test user subscribes to a new feed (Not exist)
        d = feedparser.parse(os.path.dirname(os.path.realpath(__file__)) + '/nu.nl.rss.xml')
        published_parsed = get_published_parsed(d.feed)
        with patch('feedparser.parse', return_value=d):
            url = reverse("rssfeedapi:feed_list")
            fake_url = 'https://abc.nl'
            response = api_client.post(url, data={"feed_url": fake_url})
            assert response.status_code == 201
            assert response.json().get('feed_url') == fake_url
            feed_link = response.json().get('feed')
            feed_id = feed_link.rstrip('/').split('/')[-1]  # eg: 'http://testserver/feed/3/'

            # Test feed and its entries are created in DB. New entry is added to the feed_subscription table
            assert Feed.objects.filter(feed_url=fake_url).exists()
            new_feed = Feed.objects.get(feed_url=fake_url)
            assert new_feed.id == int(feed_id)
            for key in ['title', 'link', 'description', 'language']:
                assert getattr(new_feed, key) == d.feed.get(key)
            assert new_feed.published_time == published_parsed

            for entry in d.entries:
                published_parsed = get_published_parsed(entry)
                assert Entry.objects.filter(guid=entry.id, feed=new_feed).exists()
                new_entry = Entry.objects.get(guid=entry.id, feed=new_feed)
                for key in ['title', 'link', 'description', 'author']:
                    assert getattr(new_entry, key) == entry.get(key)
                assert new_entry.published_time == published_parsed

            assert user.subscriptions.filter(feed_url=fake_url).exists()

        # Test user follows a feed which already exists in the DB
        url = reverse("rssfeedapi:feed_list")
        response = api_client.post(url, data={"feed_url": feed.feed_url})
        assert response.status_code == 201
        feed_link = response.json().get('feed')
        feed_id = feed_link.rstrip('/').split('/')[-1]  # eg: 'http://testserver/feed/3/'
        assert int(feed_id) == feed.id
        assert response.json().get('feed_url') == feed.feed_url
        assert user.subscriptions.filter(feed_url=feed.feed_url).exists()

        # Test user subscribes to an existing feed again
        response = api_client.post(url, data={"feed_url": feed.feed_url})
        assert response.status_code == 200
        feed_link = response.json().get('feed')
        feed_id = feed_link.rstrip('/').split('/')[-1]  # eg: 'http://testserver/feed/3/'
        assert int(feed_id) == feed.id
        assert response.json().get('feed_url') == feed.feed_url

        # Test user provides an invalid url
        response = api_client.post(url, data={"feed_url": 'http://invalid_rss20.xml'})
        assert response.status_code == 400

    def test_get_feed_detail(self, user, api_client, feed):
        # Setup DB: user subscribes to feed
        user.subscriptions.add(feed)

        # Test get one followed feed detail
        url = reverse("rssfeedapi:feed_detail", args=[feed.id])
        response = api_client.get(url)
        assert response.status_code == 200
        response_json = response.json()
        for key in ['feed_url', 'title', 'link', 'description', 'language', 'status', ]:
            assert response_json.get(key) == getattr(feed, key)
        assert response.json().get("published_time") == serializers.DateTimeField().to_representation(feed.published_time)
        assert response.json().get("last_updated") == serializers.DateTimeField().to_representation(feed.last_updated)
        for entry_link in response.json().get('entries'):
            entry_id = entry_link.rstrip('/').split('/')[-1]  # eg: 'http://testserver/entry/1/
            assert Entry.objects.filter(id=entry_id, feed=feed).exists()
        assert len(response.json().get('entries')) == feed.entries.count()

        # Test get Non-followed feed detail
        url = reverse("rssfeedapi:feed_detail", args=[100])
        response = api_client.get(url)
        assert response.status_code == 404

    def test_unsubscribe_feed(self, user, api_client, feed):
        # Setup DB: user subscribes to feed, all entries of the feed are read by the user
        user.subscriptions.add(feed)
        for entry in feed.entries.all():
            user.read_entries.add(entry)

        url = reverse("rssfeedapi:feed_detail", args=[feed.id])
        # Test unsubscribe to a feed
        response = api_client.delete(url)
        assert response.status_code == 204
        assert not user.subscriptions.filter(feed_url=feed.feed_url).exists()
        # Test all marked read entries have been cleared
        assert not user.read_entries.filter(feed=feed).exists()

        # Test unsubscribe to a non-existing feed
        url = reverse("rssfeedapi:feed_detail", args=[100])
        response = api_client.delete(url)
        assert response.status_code == 404

