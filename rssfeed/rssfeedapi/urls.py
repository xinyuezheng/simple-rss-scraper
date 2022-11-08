from django.urls import include, path

from .views import FeedListVew, FeedDetailView, EntryListView, EntryDetailView, EntryReadView

# router = routers.DefaultRouter()
app_name = 'rssfeedapi'
# Wire up our API using automatic URL routing.
urlpatterns = [
    # path('', include(router.urls)),
    path('feed/', FeedListVew.as_view(), name='feed_list'),
    path('feed/<int:pk>/', FeedDetailView.as_view(), name='feed_detail'),
    # path('feed/update/', FeedUpdateView.as_view(), name='feed_update'),
    path('entry/', EntryListView.as_view(), name='entry_list'),
    path('entry/<int:pk>/', EntryDetailView.as_view(), name='entry_detail'),
    path('entry/<int:pk>/read/', EntryReadView.as_view(), name='entry_read'),
]
