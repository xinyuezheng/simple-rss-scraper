from drf_yasg import openapi

from .serializers import FeedListSerializer, EntryDetailSerializer

feed_param = openapi.Parameter('feed_id', openapi.IN_QUERY,
                               description="filter entries by feed id", type=openapi.TYPE_INTEGER)
read_param = openapi.Parameter('read', openapi.IN_QUERY,
                               description="filter read/unread entries", type=openapi.TYPE_BOOLEAN)
feed_subscribed_200 = openapi.Response('Feed was already subscribed', FeedListSerializer)
feed_subscribed_201 = openapi.Response('Feed is subscribed successfully', FeedListSerializer)

entry_read_201 = openapi.Response('Entry is marked as read', EntryDetailSerializer)
entry_read_200 = openapi.Response('Entry was already marked as read', EntryDetailSerializer)
