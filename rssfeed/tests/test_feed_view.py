import pytest

from django.urls import reverse
from .utils import _create_feeds_in_db


@pytest.mark.django_db
class TestFeedView:
    def test_get_feeds(self, api_client, user, feed):
        # Set up a feed followed by the user in DB
        user.subscriptions.add(feed)

        # Test list all subscribed feeds
        url = reverse("rssfeedapi:feed_list")
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.json().get("count") == user.subscriptions.count()
        assert response.json()["results"][0]['feed_url'] == feed.feed_url

        # Test list one subscribed feed
        url = reverse("rssfeedapi:feed_detail", args=[feed.id])
        response = api_client.get(url)
        assert response.json()["feed_url"] == feed.feed_url

    def test_feed_subscription_flow(self, user, api_client, feed):
        # Test user subscribes a feed
        url = reverse("rssfeedapi:feed_list")
        response = api_client.post(url, data={"feed_url": feed.feed_url})
        assert response.status_code == 201
        assert user.subscriptions.filter(feed_url=feed.feed_url).exists()
        assert user.subscriptions.count() == 1

        # Test user subscribes to an existing feed again
        response = api_client.post(url, data={"feed_url": feed.feed_url})
        assert response.status_code == 200
        assert user.subscriptions.count() == 1

        # Test user provides invalid url
        response = api_client.post(url, data={"feed_url": 'http://invalid_rss20.xml'})
        assert response.status_code == 400

        # Test subscribed feed detail
        url = reverse("rssfeedapi:feed_detail", args=[feed.id])
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.json().get("feed_url") == feed.feed_url

        # Test unsubscribe to a feed
        response = api_client.delete(url)
        assert response.status_code == 204
        assert not user.subscriptions.filter(feed_url=feed.feed_url).exists()

        # Test unsubscribe to a non-existing feed
        url = reverse("rssfeedapi:feed_detail", args=[100])
        response = api_client.delete(url)
        assert response.status_code == 404


