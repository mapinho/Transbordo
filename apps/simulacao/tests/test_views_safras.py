import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario, SafraUnidade

User = get_user_model()


class SafrasGridViewTests(TestCase):
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
        self.safra = SafraUnidade.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            entidade_tipo='Armazém', entidade_id=self.armazem.id,
            data_inicio=datetime.date(2026, 1, 15), data_fim=datetime.date(2026, 4, 15),
        )
        self.url = reverse('simulacao:safras_grid', kwargs={'cenario_id': self.cenario.id})
        self.client.force_login(self.user)

    def test_pagina_mostra_nome_da_unidade(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # nome da unidade só aparece no payload JSON (json_script, ensure_ascii)
        self.assertContains(response, 'Armaz\\u00e9m 1')

    def test_post_atualiza_datas(self):
        linhas = [{
            'id': self.safra.id,
            'data_inicio': '2026-02-01', 'data_fim': '2026-05-01',
        }]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 200)
        self.safra.refresh_from_db()
        self.assertEqual(self.safra.data_inicio, datetime.date(2026, 2, 1))
        self.assertEqual(self.safra.data_fim, datetime.date(2026, 5, 1))

    def test_admin_vector_recebe_403(self):
        vector = User.objects.create_user(
            username='vec', email='vec@t.test', password='x', papel=User.PAPEL_ADMIN_VECTOR,
        )
        self.client.force_login(vector)
        self.assertEqual(self.client.get(self.url).status_code, 403)
