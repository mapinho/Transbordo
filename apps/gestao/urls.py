from django.urls import path

from apps.gestao import views

app_name = 'gestao'

urlpatterns = [
    path('cooperativas/', views.cooperativas, name='cooperativas'),
    path('cooperativas/nova/', views.cooperativa_nova, name='cooperativa_nova'),
    path('cooperativas/<int:cooperativa_id>/', views.cooperativa_editar, name='cooperativa_editar'),
    path('usuarios/', views.usuarios, name='usuarios'),
    path('usuarios/novo/', views.usuario_novo, name='usuario_novo'),
    path('usuarios/<int:usuario_id>/', views.usuario_editar, name='usuario_editar'),
    path('minha-cooperativa/', views.minha_cooperativa, name='minha_cooperativa'),
    path('conta/', views.conta, name='conta'),
]
