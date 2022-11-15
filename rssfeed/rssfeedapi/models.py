import logging
from datetime import timedelta

import feedparser

from django.db import models, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError, APIException

from rssfeed.settings import DAYS_RETRIEVABLE
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


class RecentEntryManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(
            published_time__gte=timezone.now()-timedelta(days=DAYS_RETRIEVABLE))


class Entry(models.Model):
    guid = models.CharField(max_length=256, unique=True, null=False, blank=False)
    title = models.CharField(max_length=512, blank=False, null=False)
    link = models.URLField(max_length=256, blank=True, null=True)
    description = models.TextField()
    author = models.URLField(max_length=64, blank=True, null=True)
    published_time = models.DateTimeField(blank=True, null=True)
    created_time = models.DateTimeField(auto_now_add=True)
    feed = models.ForeignKey('Feed', on_delete=models.CASCADE, related_name='entries')
    read_by = models.ManyToManyField('users.User', through=ReadEntry, related_name='read_entries')
    objects = models.Manager()  # The default manager.
    recent_objects = RecentEntryManager()

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
            logger.debug(f'Find Entry {entry.guid}: {entry.title} in DB')
        except cls.DoesNotExist:
            published_parsed = get_published_parsed(parsed_entry)
            entry = cls.objects.create(
                guid=parsed_entry.get('id'), title=parsed_entry.get('title', ''),
                link=parsed_entry.get('link', ''), author=parsed_entry.get('author', ''),
                description=parsed_entry.get('description', ''), published_time=published_parsed,
                feed_id=feed_id)

            logger.debug(f'New Entry {entry.guid}: {entry.title} is created')
        return entry


class Feed(models.Model):
    class Status(models.TextChoices):
        CREATING = 'creating', 'creating'
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
        indexes = [models.Index(name="feed url index", fields=["feed_url", ],)]

    def __str__(self):
        return self.feed_url

    @classmethod
    def get_or_create(cls, feed_url):
        """
        This function will only create one feed entry in 'Feed' table.
        All the belonging feed items should be created asynchronously in a separate celery task.
        """
        try:
            feed = cls.objects.get(feed_url=feed_url)
            create = False
            logger.debug(f'Find Feed: {feed.feed_url} in DB')
        except cls.DoesNotExist:
            d = feedparser.parse(feed_url)
            if d.get('bozo'):
                raise ValidationError(
                    f'Failed to parse feed: {d.get("bozo_exception")}', code=status.HTTP_400_BAD_REQUEST
                )
            published_parsed = get_published_parsed(d.feed)

            feed = cls.objects.create(feed_url=feed_url, title=d.feed.get('title', ''), link=d.feed.get('link', ''),
                                      description=d.feed.get('description', ''), language=d.feed.get('language', ''),
                                      status=Feed.Status.CREATING, published_time=published_parsed)
            create = True

        return feed, create

    def update_entries(self, parsed_entries_list, published_parsed):
        """
        create/update entries of a feed. If error occurs on one entry, roll back the transaction
        and continue for other entries.
        :param parsed_entries_list: parsed entries list from 'feedparser.parser()' (d.entreis)
        :param published_parsed: feed published time from 'feedparser.parse()' (d.published_parsed or d.updated_parsed)
        :return: a list of failed entries
        """
        failed_entries_list = []
        if self.published_time == published_parsed and self.status == Feed.Status.UPDATED:
            logger.info(f"Nothing to update: {self.title}")
            return failed_entries_list

        for entry in parsed_entries_list:  # make a new list for iteration
            # continue update other entries if one or more entries update fails
            try:
                with transaction.atomic():
                    Entry.get_or_create(parsed_entry=entry, feed_id=self.id)
            except Exception as e:
                failed_entries_list.append(entry)
                logger.error(e)

        return failed_entries_list

    def get_queryset(self):
        return self.__class__.objects.filter(id=self.id)

    def update_status(self, feed_status, published_parsed):
        """
        Updates the status of feed in the database. Use 'select_for_update' to lock the
        row until the transaction is committed, to avoid the problem of concurrency
        :param feed_status: status to be updated
        :param published_parsed: feed published time from 'feedparser.parse()' (d.published_parsed or d.updated_parsed)
        :return: current feed status
        """
        #  Operating on the self object will not work since it has already been fetched
        new_feed = self.get_queryset().select_for_update().get()
        with transaction.atomic():
            old_status = new_feed.status
            new_feed.last_updated = timezone.now()
            new_feed.status = feed_status
            if published_parsed:
                new_feed.published_time = published_parsed
            new_feed.save()

        return old_status
