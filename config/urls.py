"""URL configuration for the Transbordo project."""
from django.contrib import admin
from django.urls import include, path

from apps.integracoes.api import api as integracoes_api

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('simulacao/', include('apps.simulacao.urls')),
    path('api/v1/', integracoes_api.urls),
]
