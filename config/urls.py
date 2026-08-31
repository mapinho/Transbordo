"""URL configuration for the Transbordo project."""
from django.contrib import admin
from django.urls import include, path

from apps.core.views import healthz
from apps.integracoes.api import api as integracoes_api

urlpatterns = [
    path('admin/', admin.site.urls),
    path('healthz/', healthz, name='healthz'),
    path('accounts/', include('allauth.urls')),
    path('simulacao/', include('apps.simulacao.urls')),
    path('gestao/', include('apps.gestao.urls')),
    path('api/v1/', integracoes_api.urls),
    path('', include('apps.core.urls')),
]
