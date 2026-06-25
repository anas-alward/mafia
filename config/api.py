from apps.accounts.urls import urlpatterns as accounts_urls
from apps.friends.urls import urlpatterns as friends_urls
from apps.room.urls import urlpatterns as room_urls
from django.urls import include, path


urlpatterns = [
    path('accounts/', include((accounts_urls, 'accounts'), namespace='accounts')),
    path('rooms/', include((room_urls, 'rooms'), namespace='rooms')),
    path('friends/', include((friends_urls, 'friends'), namespace='friends')),
]