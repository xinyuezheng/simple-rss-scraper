from django.contrib import admin
from .models import Entry, Feed, FeedSubscription, ReadEntry

admin.site.register(Entry)
admin.site.register(Feed)
admin.site.register(FeedSubscription)
admin.site.register(ReadEntry)
