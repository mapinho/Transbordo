from django.urls import path

from apps.simulacao import views

app_name = 'simulacao'

urlpatterns = [
    path('cenarios/', views.cenarios_list, name='cenarios_list'),
    path('cenarios/<int:cenario_id>/fabricas/', views.fabricas_grid, name='fabricas_grid'),
    path('cenarios/<int:cenario_id>/armazens/', views.armazens_grid, name='armazens_grid'),
    path('cenarios/<int:cenario_id>/rotas/', views.rotas_grid, name='rotas_grid'),
    path('cenarios/<int:cenario_id>/previsoes/', views.previsoes_grid, name='previsoes_grid'),
    path('cenarios/<int:cenario_id>/safras/', views.safras_grid, name='safras_grid'),
]
