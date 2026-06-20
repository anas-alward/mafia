from apps.accounts.urls import urlpatterns  as accounts_urls
from django.urls import path, include


urlpatterns = [
    path('accounts/', include((accounts_urls, 'accounts'), namespace='accounts')),
]  