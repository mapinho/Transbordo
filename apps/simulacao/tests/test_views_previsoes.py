import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario, Fabrica, PrevisaoArmazem, PrevisaoFabrica

User = get_user_model()


class PrevisoesGridViewTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica 1',
            capacidade_estatica=1000, capacidade_esmagamento_diaria=100,
            capacidade_recebimento_diaria=100, limite_caminhoes=10,
            carga_media_caminhao=30, estoque_inicial=500,
        )
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém 1',
            capacidade_estatica=800, capacidade_expedicao_diaria=50, estoque_inicial=200,
        )
        self.previsao_fab = PrevisaoFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, fabrica=self.fabrica,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=300, vendas=100,
        )
        self.previsao_arm = PrevisaoArmazem.all_cooperativas.create(
            cooperativa=self.cooperativa, armazem=self.armazem,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=200, vendas=50,
        )
        self.url = reverse('simulacao:previsoes_grid', kwargs={'cenario_id': self.cenario.id})
        self.client.force_login(self.user)

    def test_pagina_mostra_as_duas_sub_grades(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # nomes só aparecem no payload JSON (json_script, ensure_ascii)
        self.assertContains(response, 'F\\u00e1brica 1')
        self.assertContains(response, 'Armaz\\u00e9m 1')

    def test_post_atualiza_ambas_previsoes_numa_transacao(self):
        linhas_fabrica = [{'id': self.previsao_fab.id, 'recebimento_produtor': 350, 'vendas': 120}]
        linhas_armazem = [{'id': self.previsao_arm.id, 'recebimento_produtor': 250, 'vendas': 60}]

        response = self.client.post(self.url, {
            'linhas_fabrica_json': json.dumps(linhas_fabrica),
            'linhas_armazem_json': json.dumps(linhas_armazem),
        })

        self.assertEqual(response.status_code, 200)
        self.previsao_fab.refresh_from_db()
        self.previsao_arm.refresh_from_db()
        self.assertEqual(self.previsao_fab.recebimento_produtor, 350)
        self.assertEqual(self.previsao_arm.vendas, 60)

    def test_previsao_de_outra_cooperativa_nao_aparece(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        outro_cenario = Cenario.all_cooperativas.create(cooperativa=outra_cooperativa, nome='Cenário B')
        outra_fabrica = Fabrica.all_cooperativas.create(
            cooperativa=outra_cooperativa, cenario=outro_cenario, nome='Fábrica B',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )
        PrevisaoFabrica.all_cooperativas.create(
            cooperativa=outra_cooperativa, fabrica=outra_fabrica,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=999, vendas=999,
        )

        response = self.client.get(self.url)

        self.assertNotContains(response, 'F\\u00e1brica B')
