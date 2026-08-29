import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario, Fabrica, Rota

User = get_user_model()


class RotasGridViewTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', email='usuaria@coop-a.test', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém 1',
            capacidade_estatica=800, capacidade_expedicao_diaria=50, estoque_inicial=200,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica 1',
            capacidade_estatica=1000, capacidade_esmagamento_diaria=100,
            capacidade_recebimento_diaria=100, limite_caminhoes=10,
            carga_media_caminhao=30, estoque_inicial=500,
        )
        self.rota = Rota.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            armazem=self.armazem, fabrica=self.fabrica,
            distancia_km=120, custo_frete_ton=45, custo_frete_entressafra=30,
        )
        self.url = reverse('simulacao:rotas_grid', kwargs={'cenario_id': self.cenario.id})
        self.client.force_login(self.user)

    def test_pagina_mostra_origem_e_destino_pelo_nome(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # nomes só aparecem no payload JSON (json_script, ensure_ascii)
        self.assertContains(response, 'Armaz\\u00e9m 1')
        self.assertContains(response, 'F\\u00e1brica 1')

    def test_post_atualiza_custos_e_distancia(self):
        linhas = [{
            'id': self.rota.id,
            'distancia_km': 150, 'custo_frete_ton': 50, 'custo_frete_entressafra': 35,
        }]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 200)
        self.rota.refresh_from_db()
        self.assertEqual(self.rota.distancia_km, 150)
        self.assertEqual(self.rota.custo_frete_entressafra, 35)
