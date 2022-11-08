from drf_yasg import openapi

from .serializers import FeedListSerializer

feed_param = openapi.Parameter('feed_id', openapi.IN_QUERY,
                               description="filter entries by feed id", type=openapi.TYPE_INTEGER)
read_param = openapi.Parameter('read', openapi.IN_QUERY,
                               description="filter read/unread entries", type=openapi.TYPE_BOOLEAN)
feed_subscribed_200 = openapi.Response('Feed is already subscribed', FeedListSerializer)
feed_subscribed_201 = openapi.Response('Feed is successfully subscribed', FeedListSerializer)
