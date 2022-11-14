import logging

import feedparser

from django.db import models
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from .utils import get_published_parsed
logger = logging.getLogger(__name__)


class FeedSubscription(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    feed = models.ForeignKey('Feed', on_delete=models.CASCADE)
    subscribed_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-id', )
        unique_together = ('user', 'feed',)

    def __str__(self):
        return f'{self.user.username}:{self.feed.feed_url}'


class ReadEntry(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    entry = models.ForeignKey('Entry', on_delete=models.CASCADE)
    read_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'entry',)
        verbose_name = 'read entry'
        verbose_name_plural = 'read entries'


class Entry(models.Model):
    guid = models.CharField(max_length=256, unique=True, null=False)
    title = models.CharField(max_length=512, blank=True, null=True)
    link = models.URLField(max_length=256, blank=True, null=True)
    description = models.TextField()
    author = models.URLField(max_length=64, blank=True, null=True)
    published_time = models.DateTimeField(blank=True, null=True)
    created_time = models.DateTimeField(auto_now_add=True)
    feed = models.ForeignKey('Feed', on_delete=models.CASCADE, related_name='entries')
    read_by = models.ManyToManyField('users.User', through=ReadEntry, related_name='read_entries')

    class Meta:
        ordering = ('-published_time', )
        verbose_name_plural = 'entries'
        indexes = [models.Index(name="entry guid index", fields=["guid", ],)]

    def __str__(self):
        return self.title

    @classmethod
    def get_or_create(cls, parsed_entry, feed_id):

        try:
            entry = cls.objects.get(guid=parsed_entry.get('id'))
            logger.info(f'Find Entry {entry.guid}: {entry.title} in DB')
        except cls.DoesNotExist:
            published_parsed = get_published_parsed(parsed_entry)
            entry = cls.objects.create(guid=parsed_entry.get('id'), title=parsed_entry.get('title', ''),
                                         link=parsed_entry.get('link', ''),
                                         author=parsed_entry.get('author', ''),
                                         description=parsed_entry.get('description', ''),
                                         published_time=published_parsed, feed_id=feed_id)
            logger.info(f'New Entry {entry.guid}: {entry.title} is created')
        return entry


class Feed(models.Model):
    class Status(models.TextChoices):
        UPDATED = 'updated', 'Updated'
        ERROR = 'error', 'Error'

    feed_url = models.URLField(max_length=256, unique=True)
    title = models.CharField(max_length=512, blank=True, null=True)
    link = models.URLField(max_length=256, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    published_time = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(auto_now_add=True)
    language = models.CharField(max_length=16, blank=True, null=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPDATED)
    subscribers = models.ManyToManyField('users.User', through=FeedSubscription, related_name='subscriptions')

    class Meta:
        indexes = [models.Index(name="feed_url index", fields=["feed_url", ],)]

    def __str__(self):
        return self.feed_url

    @classmethod
    def get_or_create(cls, feed_url):
        try:
            feed = cls.objects.get(feed_url=feed_url)
            logger.info(f'Find Feed: {feed.feed_url} in DB')
        except cls.DoesNotExist:
            d = feedparser.parse(feed_url)
            if d.get('bozo'):
                raise ValidationError(f'rss feedparser failed: {d.get("bozo_exception")}',
                                   code=status.HTTP_400_BAD_REQUEST)

            published_parsed = get_published_parsed(d.feed)

            feed = cls.objects.create(feed_url=feed_url, title=d.feed.get('title', ''), link=d.feed.get('link', ''),
                                      description=d.feed.get('description', ''), language=d.feed.get('language', ''),
                                      published_time=published_parsed)
            logger.info(f'New Feed: {feed.feed_url} created')
            for entry in d.entries:
                Entry.get_or_create(parsed_entry=entry, feed_id=feed.id)

        return feed
