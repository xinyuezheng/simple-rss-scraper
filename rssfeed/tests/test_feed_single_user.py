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


@pytest.mark.django_db
class TestEntryView:
    def test_get_entries(self, user, api_client):
        feeds = _create_feeds_in_db(3)
        user.subscriptions.add(feeds[0])
        user.subscriptions.add(feeds[1])

        # Test list all subscribed entries
        url = reverse("rssfeedapi:entry_list")
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.json().get("count") == feeds[0].entries.count() + feeds[1].entries.count()

        # Test list one subscribed entries
        entry = feeds[1].entries.first()
        url = reverse("rssfeedapi:entry_detail", args=[entry.id])
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.json().get("link") == entry.link

        # Test list one of not subscribed entries
        entry = feeds[2].entries.first()
        url = reverse("rssfeedapi:entry_detail", args=[entry.id])
        response = api_client.get(url)
        assert response.status_code == 404

    def test_entries_filters(self, user, api_client):
        # Setup in DB: User subscribes to feed0 and feed1, but not feed2. User reads the first entry of feed.
        feeds = _create_feeds_in_db(3)
        user.subscriptions.add(feeds[0])
        user.subscriptions.add(feeds[1])
        read_entry = feeds[0].entries.first()
        user.read_entries.add(read_entry)

        url = reverse("rssfeedapi:entry_list")

        # Test feed_id filter. feed is subscribed
        query_param = f'?feed_id={feeds[0].id}'
        response = api_client.get(url+query_param)
        assert response.status_code == 200
        assert response.json().get("count") == feeds[0].entries.count()

        # Test feed_id filter. feed3 is not subscribed
        query_param = f'?feed_id={feeds[2].id}'
        response = api_client.get(url+query_param)
        assert response.status_code == 200
        assert response.json().get("count") == 0

        # Test read filter is True. One entry has been read by user in DB
        query_param = '?read=True'
        response = api_client.get(url+query_param)
        assert response.status_code == 200
        assert response.json().get("count") == 1
        assert response.json()['results'][0]["link"] == read_entry.link

        # Test read filter is False. Not read entries == all subscribed entries - 1 read entry
        query_param = '?read=False'
        response = api_client.get(url+query_param)
        assert response.status_code == 200
        assert response.json().get("count") == feeds[0].entries.count() + feeds[1].entries.count() - 1

        # Test read filter per feed
        query_param = f'?feed_id={feeds[0].id}&read=True'
        response = api_client.get(url+query_param)
        assert response.status_code == 200
        assert response.json().get("count") == 1
        assert response.json()['results'][0]["link"] == read_entry.link

        query_param = f'?feed_id={feeds[0].id}&read=False'
        response = api_client.get(url+query_param)
        assert response.status_code == 200
        assert response.json().get("count") == feeds[0].entries.count() - 1

        query_param = f'?feed_id={feeds[1].id}&read=True'
        response = api_client.get(url+query_param)
        assert response.status_code == 200
        assert response.json().get("count") == 0

        query_param = f'?feed_id={feeds[1].id}&read=False'
        response = api_client.get(url+query_param)
        assert response.status_code == 200
        assert response.json().get("count") == feeds[1].entries.count()

        # Test invalid query parameter
        query_param = f'?feed_id={feeds[1].id}&read=Invalid'
        response = api_client.get(url+query_param)
        assert response.status_code == 400

        query_param = f'?feed_id=Invalid&read=True'
        response = api_client.get(url+query_param)
        assert response.status_code == 400


@pytest.mark.django_db
class TestEntryReadView:
    def test_mark_entry_read(self, user, api_client, feed):
        user.subscriptions.add(feed)

        # Test mark entry as read
        entry = feed.entries.first()
        url = reverse("rssfeedapi:entry_read", args=[entry.id])
        response = api_client.post(url)
        assert response.status_code == 201
        assert user.read_entries.filter(id=entry.id).exists()

        # Test mark entry as read again
        response = api_client.post(url)
        assert response.status_code == 200
        assert user.read_entries.filter(id=entry.id).exists()

        # Test Entry Detail Serializer 'read' field is set
        url = reverse("rssfeedapi:entry_detail", args=[entry.id])
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.json().get("read")

        # Test mark not subscribed entry as read
        feeds = _create_feeds_in_db(1)
        entry = feeds[0].entries.first()
        url = reverse("rssfeedapi:entry_read", args=[entry.id])
        response = api_client.post(url)
        assert response.status_code == 404
        assert not user.read_entries.filter(id=entry.id).exists()



