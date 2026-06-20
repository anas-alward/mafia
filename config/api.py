from apps.accounts.urls import urlpatterns as accounts_urls
from apps.room.urls import urlpatterns as room_urls
from django.urls import path, include


urlpatterns = [
    path('accounts/', include((accounts_urls, 'accounts'), namespace='accounts')),
    path('rooms/', include((room_urls, 'rooms'), namespace='rooms')),
]