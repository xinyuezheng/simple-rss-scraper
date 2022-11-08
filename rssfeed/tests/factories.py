import datetime

import factory
from django.utils import timezone
from faker import Faker

from rssfeed.settings import DAYS_RETRIEVABLE
from rssfeedapi.models import Feed, Entry
from users.models import User


fake = Faker()


class FeedFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Feed
        django_get_or_create = ['feed_url']

    feed_url = fake.image_url()
    title = fake.text(10)
    link = fake.image_url()
    description = fake.text(20)
    published_time = fake.date_time(tzinfo=datetime.timezone.utc)
    last_updated = timezone.now()


class EntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Entry
        django_get_or_create = ['guid']
    guid = fake.image_url()
    link = fake.image_url()
    title = fake.text(10)
    description = fake.text(20)
    published_time = timezone.now() - datetime.timedelta(days=DAYS_RETRIEVABLE-1)
    feed = factory.SubFactory(FeedFactory)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ('username',)
    username = 'xinyue'
    email = 'xinyue@api.com'
    password = fake.text(10)
