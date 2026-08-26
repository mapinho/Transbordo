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
    path('cenarios/<int:cenario_id>/simulacao/', views.simulacao_tab, name='simulacao_tab'),
    path(
        'cenarios/<int:cenario_id>/simulacao/executar/',
        views.simulacao_executar, name='simulacao_executar',
    ),
    path(
        'cenarios/<int:cenario_id>/simulacao/status/',
        views.simulacao_status, name='simulacao_status',
    ),
    path('carga/', views.carga_upload, name='carga'),
    path('carga/template/', views.carga_template, name='carga_template'),
    path('carga/<str:token>/', views.carga_preview, name='carga_preview'),
]
