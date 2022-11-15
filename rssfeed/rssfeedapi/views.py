import logging
from datetime import timedelta

from celery import group
from django.db.models import Prefetch
from django.http import Http404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from drf_yasg.utils import swagger_auto_schema, no_body

from rest_framework import status
from rest_framework.generics import ListCreateAPIView, \
    ListAPIView, RetrieveAPIView, CreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from rssfeed.settings import DAYS_RETRIEVABLE
from .swagger_utils import feed_subscribed_200, feed_subscribed_201, feed_param, read_param, entry_read_200, \
    entry_read_201
from .tasks import update_feed

from .serializers import FeedListSerializer, FeedDetailSerializer, EntryFilterSerializer, \
    EntryListSerializer, EntryDetailSerializer
from .models import Entry, Feed, FeedSubscription
logger = logging.getLogger(__name__)


@method_decorator(name='get',
                  decorator=[swagger_auto_schema(
                      operation_summary="List all feeds followed by a user, order by the subscribed date",),
                             cache_page(60*60*2),
                             vary_on_headers("Authorization",)])
@method_decorator(name='post', decorator=swagger_auto_schema(
    operation_summary="User subscribes to a new feed",
    operation_description="Add a feed to user's subscription list. "
                          "Create a new feed in the database if not exists",
    responses={200: feed_subscribed_200, 201: feed_subscribed_201, 400: 'rss feedparser error'},
))
class FeedListVew(ListCreateAPIView):
    serializer_class = FeedListSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return FeedSubscription.objects.none()
        return FeedSubscription.objects.filter(user=self.request.user).select_related('feed')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        feed_url = serializer.validated_data['feed']['feed_url']
        feed, create = Feed.get_or_create(feed_url)
        if create:  # update entreis at background
            update_feed.apply_async(args=(feed.feed_url,), queue='force_feed_update',)

        feed_subs = FeedSubscription.objects.filter(feed=feed, user=self.request.user).first()
        if feed_subs:
            return_status = status.HTTP_200_OK
        else:
            feed_subs = FeedSubscription.objects.create(feed=feed, user=self.request.user)
            return_status = status.HTTP_201_CREATED

        fs_serializer = self.serializer_class(instance=feed_subs, context={'request': request})
        headers = self.get_success_headers(fs_serializer.data)
        return Response(fs_serializer.data, status=return_status, headers=headers)


@method_decorator(name='get', decorator=swagger_auto_schema(
    operation_summary=f"Show one followed feed details. "
                      f"Only include entries published in recent {DAYS_RETRIEVABLE} days of the feed",
))
@method_decorator(name='put', decorator=swagger_auto_schema(
    operation_summary="User manually updates the feed",
    request_body=no_body,
    responses={200: "Feed will be updated at background"}
))
@method_decorator(name='delete', decorator=swagger_auto_schema(
    operation_summary="User unsubscribes the feed",
    responses={204: "User unsubscribes feed successfully"}
))
class FeedDetailView(RetrieveUpdateDestroyAPIView):
    serializer_class = FeedDetailSerializer
    http_method_names = ['get', 'put', 'delete']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Feed.objects.none()

        return self.request.user.subscriptions.prefetch_related(
            Prefetch('entries',
                     queryset=Entry.recent_objects.all()
                     )
        )

    def perform_destroy(self, serializer):
        feed = self.get_object()
        self.request.user.subscriptions.remove(feed)
        self.request.user.read_entries.remove(*Entry.objects.filter(feed=feed))

    def update(self, request, *args, **kwargs):
        feed = self.get_object()
        update_feed.apply_async(args=(feed.feed_url,), queue='force_feed_update',)
        return Response(f"Feed {feed.id} will be updated at background")

# debug purpose
# class FeedUpdateView(APIView):
#     @swagger_auto_schema(operation_summary="Update all feeds subscribed by the user",
#                          request_body=no_body,
#                          responses={200: "Feed will be updated at background"})
#     def post(self, request, *args, **kwargs):
#         feeds = self.request.user.subscriptions
#         group(update_feed.s(feed.id) for feed in feeds).apply_async(queue='force_feed_update')
#         return Response("All feeds will be updated at background", status=status.HTTP_200_OK)


@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        operation_summary=f"Get details of an entry which was published in recent {DAYS_RETRIEVABLE} days ",),
)
class EntryDetailView(RetrieveAPIView):
    serializer_class = EntryDetailSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"user": self.request.user})
        return context

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Entry.objects.none()

        return Entry.recent_objects.filter(
            feed__in=self.request.user.subscriptions.values_list('id'),
        ).prefetch_related('read_by')


class EntryReadView(APIView):
    @swagger_auto_schema(operation_summary=f"Mark one entry published in recent {DAYS_RETRIEVABLE} days as read",
                         request_body=no_body,
                         responses={200: entry_read_200, 201: entry_read_201})
    def post(self, request, pk, **kargs):
        try:
            entry = Entry.recent_objects.get(
                id=pk, feed__in=self.request.user.subscriptions.values_list('id'),
            )

            if entry.read_by.filter(id=request.user.id).exists():
                return_status = status.HTTP_200_OK
            else:
                entry.read_by.add(request.user)
                return_status = status.HTTP_201_CREATED

            entry_serializer = EntryDetailSerializer(entry,
                                                     context={'request': request, 'user': request.user})
            return Response(entry_serializer.data, status=return_status)

        except Entry.DoesNotExist:
            raise Http404


@method_decorator(
    name='get',
    decorator=[
        swagger_auto_schema(
                operation_summary=f"List followed entries published in recent {DAYS_RETRIEVABLE} days, order by "
                                  f"the published date",
                operation_description="'feed_id': Filter entries per feed. 'read': Filter read/unread entries. "
                                      "Combine those to filter read/unread entries globally or per feed",
                manual_parameters=[feed_param, read_param],),
        cache_page(60 * 60 * 2),
        vary_on_headers("Authorization", )]
)
class EntryListView(ListAPIView):
    serializer_class = EntryListSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Entry.objects.none()

        filter_serializer = EntryFilterSerializer(data=self.request.query_params)

        if filter_serializer.is_valid(raise_exception=True):
            read = filter_serializer.validated_data.get('read', None)
            feed_id = filter_serializer.validated_data.get('feed_id', None)

        entries = Entry.recent_objects.filter(
            feed__in=self.request.user.subscriptions.values_list('id'),
        )

        if read:
            entries = entries.filter(read_by=self.request.user)

        if read == False:  # Explicit False, Not None
            entries = entries.exclude(read_by=self.request.user)

        if feed_id:
            entries = entries.filter(feed_id=feed_id)

        return entries
