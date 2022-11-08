from django.utils.decorators import method_decorator
from drf_yasg.utils import swagger_auto_schema

from rest_framework import permissions
from rest_framework.generics import CreateAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED

from . import serializers
from .models import User


@method_decorator(name='post', decorator=swagger_auto_schema(
    operation_summary="Create a user",
    responses={201: "User is created successfully", 400: "User already exists"}
))
class UserRegistrationView(CreateAPIView):
    # This view should be accessible also for unauthenticated users.
    permission_classes = (permissions.AllowAny,)
    serializer_class = serializers.UserSerializer

    def create(self, request, *args, **kwargs):
        user_serializer = self.get_serializer(data=request.data)
        user_serializer.is_valid(raise_exception=True)

        username = user_serializer.validated_data.get('username')
        password = user_serializer.validated_data.get('password')
        email = user_serializer.validated_data.get('email')

        User.objects.create_user(username=username, email=email, password=password)

        return Response(f'user {username} is created', status=HTTP_201_CREATED)


@method_decorator(name='get', decorator=swagger_auto_schema(
    operation_summary="Show current user",
))
class ProfileView(RetrieveAPIView):
    serializer_class = serializers.UserProfileSerializer

    def get_object(self):
        return self.request.user
