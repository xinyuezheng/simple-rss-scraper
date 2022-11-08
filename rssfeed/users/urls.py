from django.urls import path

from .views import UserRegistrationView, ProfileView

app_name = 'users'

urlpatterns = [
    path('user/registration/', UserRegistrationView.as_view(), name='user_registration'),
    path('user/profile/', ProfileView.as_view(), name='user_profile'),
]
