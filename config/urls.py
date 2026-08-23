"""URL configuration for the Transbordo project."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('simulacao/', include('apps.simulacao.urls')),
]
