import pytest
from rest_framework.reverse import reverse
from rest_framework.test import APIClient

from users.models import User


@pytest.mark.django_db
def test_registration_and_authentication():
    client = APIClient()

    # Test user registration
    url = reverse("users:user_registration")
    username = 'testuser'
    password = '!qwe123'
    response = client.post(url, data={'username': username, 'password': password, 'email': 'test@api.com'})
    assert response.status_code == 201
    assert User.objects.filter(username=username).exists()

    # Test unauthorized user accessing endpoints
    url = reverse("rssfeedapi:feed_list")
    response = client.get(url)
    assert response.status_code == 401

    # Test retrieve access token
    url = reverse("token_obtain_pair")
    response = client.post(url, data={'username': username, 'password': password})
    assert response.status_code == 200
    access_token = response.json().get('access')
    refresh_token = response.json().get('refresh')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

    # User authenticated
    url = reverse("rssfeedapi:feed_list")
    response = client.get(url)
    assert response.status_code == 200

    # Test refresh token
    client = APIClient()  # new instance of client to clear up credentials in HTTP header
    url = reverse("token_refresh")
    response = client.post(url, data={'refresh': refresh_token})
    assert response.status_code == 200
    new_access_token = response.json().get('access')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {new_access_token}')

    # User authenticated again
    url = reverse("rssfeedapi:feed_list")
    response = client.get(url)
    assert response.status_code == 200
