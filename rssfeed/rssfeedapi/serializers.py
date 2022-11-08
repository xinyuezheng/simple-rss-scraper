from rest_framework import serializers

from .models import Entry, Feed, FeedSubscription


class EntryListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entry
        fields = ('id', 'title', 'link',  'published_time')
        read_only_fields = ['id', 'title', 'link', 'published_time']


class EntryDetailSerializer(serializers.HyperlinkedModelSerializer):
    read = serializers.BooleanField(default=False)

    class Meta:
        model = Entry
        fields = ('id', 'title', 'link', 'description', 'guid', 'feed', 'author', 'published_time', 'created_time',
                  'read',)
        read_only_fields = ['id', 'title', 'link', 'description', 'guid', 'feed', 'author', 'published_time',
                            'created_time', 'read']

        extra_kwargs = {
            'feed': {'view_name': 'rssfeedapi:feed_detail'}
        }


class EntryFilterSerializer(serializers.Serializer):
    feed_id = serializers.IntegerField(required=False)
    read = serializers.BooleanField(allow_null=True, default=None, required=False)


class FeedListSerializer(serializers.HyperlinkedModelSerializer):
    subscription_id = serializers.IntegerField(source='id', read_only=True)
    feed_url = serializers.CharField(source='feed.feed_url')

    class Meta:
        model = FeedSubscription
        fields = ('subscription_id', 'feed_url', 'feed', 'subscribed_time')
        read_only_fields = ('subscription_id', 'feed', 'subscribed_time')

        extra_kwargs = {
            'feed': {'view_name': 'rssfeedapi:feed_detail'},
        }


class FeedDetailSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Feed
        fields = ('id', 'feed_url', 'title', 'link', 'description', 'language',
                  'published_time', 'last_updated', 'status', 'entries',)
        read_only_fields = ('id', 'feed_url', 'title', 'link', 'description', 'language',
                            'published_time', 'last_updated', 'status', 'entries', )

        extra_kwargs = {
            'entries': {'view_name': 'rssfeedapi:entry_detail'}
        }
