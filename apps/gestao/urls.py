from django.urls import path

from apps.gestao import views

app_name = 'gestao'

urlpatterns = [
    path('cooperativas/', views.cooperativas, name='cooperativas'),
    path('cooperativas/nova/', views.cooperativa_nova, name='cooperativa_nova'),
    path('cooperativas/<int:cooperativa_id>/', views.cooperativa_editar, name='cooperativa_editar'),
    path('conta/', views.conta, name='conta'),
]
