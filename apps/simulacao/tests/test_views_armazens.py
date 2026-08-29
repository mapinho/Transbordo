import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario

User = get_user_model()


class ArmazensGridViewTests(TestCase):
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
        self.url = reverse('simulacao:armazens_grid', kwargs={'cenario_id': self.cenario.id})
        self.client.force_login(self.user)

    def test_pagina_completa(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # nome do armazém só aparece no payload JSON (json_script, ensure_ascii)
        self.assertContains(response, 'Armaz\\u00e9m 1')

    def test_post_atualiza_armazem_existente_incluindo_nome(self):
        linhas = [{
            'id': self.armazem.id, 'nome': 'Armazém Renomeado',
            'capacidade_estatica': 900, 'capacidade_expedicao_diaria': 60, 'estoque_inicial': 250,
        }]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 200)
        self.armazem.refresh_from_db()
        self.assertEqual(self.armazem.nome, 'Armazém Renomeado')
        self.assertEqual(self.armazem.capacidade_estatica, 900)

    def test_post_sem_id_cria_novo_armazem(self):
        linhas = [{
            'id': None, 'nome': 'Armazém Novo',
            'capacidade_estatica': 500, 'capacidade_expedicao_diaria': 40, 'estoque_inicial': 0,
        }]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 200)
        novo = Armazem.all_cooperativas.get(cenario_id=self.cenario.id, nome='Armazém Novo')
        self.assertEqual(novo.capacidade_estatica, 500)

    def test_post_linha_sem_id_e_sem_nome_e_ignorada(self):
        linhas = [{'id': None, 'nome': '', 'capacidade_estatica': 1, 'capacidade_expedicao_diaria': 1, 'estoque_inicial': 0}]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Armazem.all_cooperativas.filter(cenario_id=self.cenario.id).count(), 1)

    def test_usuario_fabrica_recebe_403(self):
        fabril = User.objects.create_user(
            username='fab', email='fab@coop-a.test', password='x',
            cooperativa=self.cooperativa, papel=User.PAPEL_USUARIO_FABRICA,
        )
        self.client.force_login(fabril)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_usuario_armazem_edita(self):
        armazenista = User.objects.create_user(
            username='arm', email='arm@coop-a.test', password='x',
            cooperativa=self.cooperativa, papel=User.PAPEL_USUARIO_ARMAZEM,
        )
        self.client.force_login(armazenista)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_admin_vector_recebe_403(self):
        vector = User.objects.create_user(
            username='vec', email='vec@t.test', password='x', papel=User.PAPEL_ADMIN_VECTOR,
        )
        self.client.force_login(vector)
        self.assertEqual(self.client.get(self.url).status_code, 403)
