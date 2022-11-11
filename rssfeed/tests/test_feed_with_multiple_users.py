import pytest
from rest_framework.reverse import reverse

from .utils import _create_authorized_users, _create_feeds_in_db


@pytest.mark.django_db
class TestFeedView:
    def test_get_feeds(self):
        # Set up in DB: feed0 is followed by user0. feed1 is followed by both user0 and user1
        users, clients = _create_authorized_users(2)
        feeds = _create_feeds_in_db(2)
        users[0].subscriptions.add(feeds[0])
        users[0].subscriptions.add(feeds[1])
        users[1].subscriptions.add(feeds[1])

        # Test list all subscribed feeds
        url = reverse("rssfeedapi:feed_list")

        response = clients[0].get(url)
        assert response.status_code == 200
        assert response.json().get("count") == users[0].subscriptions.count()

        response = clients[1].get(url)
        assert response.status_code == 200
        assert response.json().get("count") == users[1].subscriptions.count()

        # Test list one feed, user0 gets 200, but user1 gets 404
        url = reverse("rssfeedapi:feed_detail", args=[feeds[0].id])
        response = clients[0].get(url)
        assert response.status_code == 200
        assert response.json()["feed_url"] == feeds[0].feed_url
        response = clients[1].get(url)
        assert response.status_code == 404

        # Test one feed. Both user gets 200
        url = reverse("rssfeedapi:feed_detail", args=[feeds[1].id])
        response = clients[0].get(url)
        assert response.status_code == 200
        response = clients[1].get(url)
        assert response.status_code == 200

    def test_feed_subscription_flow(self):
        users, clients = _create_authorized_users(2)
        feeds = _create_feeds_in_db(2)

        # Test user0 subscribes to feed0, user1 subscribes to both feed0 and feed1
        url = reverse("rssfeedapi:feed_list")
        response = clients[0].post(url, data={"feed_url": feeds[0].feed_url})
        assert response.status_code == 201
        assert users[0].subscriptions.filter(feed_url=feeds[0].feed_url).exists()
        assert users[0].subscriptions.count() == 1

        response = clients[1].post(url, data={"feed_url": feeds[0].feed_url})
        assert response.status_code == 201
        assert users[1].subscriptions.filter(feed_url=feeds[0].feed_url).exists()
        assert users[1].subscriptions.count() == 1

        response = clients[1].post(url, data={"feed_url": feeds[1].feed_url})
        assert response.status_code == 201
        assert users[1].subscriptions.filter(feed_url=feeds[1].feed_url).exists()
        assert users[1].subscriptions.count() == 2

        # Test subscribed feed detail
        url = reverse("rssfeedapi:feed_detail", args=[feeds[1].id])
        response = clients[0].get(url)
        assert response.status_code == 404
        response = clients[1].get(url)
        assert response.status_code == 200

        # Test user0 unsubscribes to a feed0, but feed0 is still in user1's subscription list
        url = reverse("rssfeedapi:feed_detail", args=[feeds[0].id])
        response = clients[0].delete(url)
        assert response.status_code == 204
        response = clients[0].get(url)
        assert response.status_code == 404
        response = clients[1].get(url)
        assert response.status_code == 200


@pytest.mark.django_db
class TestEntryView:
    def test_get_entries(self):
        # user0 subscribes to feed0, user1 subscribes to both feed0 and feed1
        users, clients = _create_authorized_users(2)
        feeds = _create_feeds_in_db(2)
        users[0].subscriptions.add(feeds[0])
        users[1].subscriptions.add(feeds[0])
        users[1].subscriptions.add(feeds[1])

        # Test list all subscribed entries
        url = reverse("rssfeedapi:entry_list")
        response = clients[0].get(url)
        assert response.status_code == 200
        assert response.json().get("count") == feeds[0].entries.count()
        response = clients[1].get(url)
        assert response.status_code == 200
        assert response.json().get("count") == feeds[0].entries.count() + feeds[1].entries.count()

        # Test get entries from feed1. user0 gets 404 (not subscribed), user1 gets 200
        entry = feeds[1].entries.first()
        url = reverse("rssfeedapi:entry_detail", args=[entry.id])
        response = clients[0].get(url)
        assert response.status_code == 404
        response = clients[1].get(url)
        assert response.status_code == 200

    def test_entries_filters(self):
        # Setup in DB: User0 reads 1st entry in feed0, user1 not.
        feeds = _create_feeds_in_db(2)
        users, clients = _create_authorized_users(2)
        users[0].subscriptions.add(feeds[0])
        users[1].subscriptions.add(feeds[0])
        read_entry = feeds[0].entries.first()
        users[0].read_entries.add(read_entry)

        url = reverse("rssfeedapi:entry_list")
        query_param = '?read=True'

        response = clients[0].get(url+query_param)
        assert response.status_code == 200
        assert response.json().get("count") == 1
        response = clients[1].get(url+query_param)
        assert response.status_code == 200
        assert response.json().get("count") == 0

        query_param = '?read=False'
        response = clients[0].get(url+query_param)
        assert response.status_code == 200
        assert response.json().get("count") == feeds[0].entries.count() - 1
        response = clients[1].get(url+query_param)
        assert response.status_code == 200
        assert response.json().get("count") == feeds[0].entries.count()

    def test_mark_entry_read(self):
        # Setup in DB: User0 and user1 subscribes to feed0
        feeds = _create_feeds_in_db(1)
        users, clients = _create_authorized_users(2)
        users[0].subscriptions.add(feeds[0])
        users[1].subscriptions.add(feeds[0])
        read_entry = feeds[0].entries.first()

        # Test user0 marks entry as read
        url = reverse("rssfeedapi:entry_read", args=[read_entry.id])
        response = clients[0].post(url)
        assert response.status_code == 201
        # Check user0 reads the entry, but user1 not
        url = reverse("rssfeedapi:entry_detail", args=[read_entry.id])
        response = clients[0].get(url)
        assert response.json().get("read")
        response = clients[1].get(url)
        assert not response.json().get("read")

