import random

from faker import Faker

from .factories import FeedFactory, EntryFactory, UserFactory
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


def _create_feeds_in_db(n):
    feeds = []
    for _ in range(n):
        feed = FeedFactory(feed_url=Faker().image_url())

        rand_entries = random.randint(1, 9)
        for _ in range(rand_entries):
            e = EntryFactory(guid=Faker().image_url())
            feed.entries.add(e)
        feeds.append(feed)

    return feeds


def _create_authorized_users(n):
    users = []
    clients = []
    for _ in range(n):
        user = UserFactory(username=Faker().text(10))
        client = APIClient()
        refresh = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

        users.append(user)
        clients.append(client)

    return users,  clients

