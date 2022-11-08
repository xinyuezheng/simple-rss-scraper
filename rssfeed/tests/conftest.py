import pytest
from faker import Faker

from .factories import FeedFactory, EntryFactory, UserFactory
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from rssfeed.celery import app


@pytest.fixture
def feed():
    feed = FeedFactory(feed_url=Faker().image_url())

    for _ in range(3):
        e = EntryFactory(guid=Faker().image_url())
        feed.entries.add(e)

    return feed


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def api_client():
    user = UserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

    return client

@pytest.fixture()
def celery_app(request):
    app.conf.update(CELERY_TASK_ALWAYS_EAGER=True)
    return app

