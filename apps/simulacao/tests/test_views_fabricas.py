import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Cenario, Fabrica

User = get_user_model()


class FabricasGridViewTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', email='usuaria@coop-a.test', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica 1',
            capacidade_estatica=1000, capacidade_esmagamento_diaria=100,
            capacidade_recebimento_diaria=100, limite_caminhoes=10,
            carga_media_caminhao=30, estoque_inicial=500,
        )
        self.url = reverse('simulacao:fabricas_grid', kwargs={'cenario_id': self.cenario.id})

    def test_requer_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_pagina_completa_sem_htmx(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html')

    def test_partial_com_htmx_nao_repete_html_base(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<html')
        # A grade é renderizada no cliente via Tabulator a partir do JSON em
        # json_script; o HTML gerado no servidor não contém o texto legível
        # diretamente, só o payload JSON (escapado ensure_ascii pelo Django).
        self.assertContains(response, 'F\\u00e1brica 1')

    def test_cenario_de_outra_cooperativa_404(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        cenario_b = Cenario.all_cooperativas.create(cooperativa=outra_cooperativa, nome='Cenário B')
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('simulacao:fabricas_grid', kwargs={'cenario_id': cenario_b.id})
        )

        self.assertEqual(response.status_code, 404)

    def test_post_atualiza_fabrica_existente(self):
        self.client.force_login(self.user)
        linhas = [{
            'id': self.fabrica.id,
            'capacidade_estatica': 1500, 'capacidade_esmagamento_diaria': 120,
            'capacidade_recebimento_diaria': 110, 'limite_caminhoes': 12,
            'carga_media_caminhao': 32, 'estoque_inicial': 600,
        }]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 200)
        self.fabrica.refresh_from_db()
        self.assertEqual(self.fabrica.capacidade_estatica, 1500)
        self.assertEqual(self.fabrica.limite_caminhoes, 12)

    def test_post_com_valor_invalido_nao_salva_nada(self):
        self.client.force_login(self.user)
        linhas = [{
            'id': self.fabrica.id,
            'capacidade_estatica': 'não-é-um-número', 'capacidade_esmagamento_diaria': 120,
            'capacidade_recebimento_diaria': 110, 'limite_caminhoes': 12,
            'carga_media_caminhao': 32, 'estoque_inicial': 600,
        }]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 400)
        self.fabrica.refresh_from_db()
        self.assertEqual(self.fabrica.capacidade_estatica, 1000)

    def test_usuario_armazem_recebe_403(self):
        armazenista = User.objects.create_user(
            username='arm', email='arm@coop-a.test', password='x',
            cooperativa=self.cooperativa, papel=User.PAPEL_USUARIO_ARMAZEM,
        )
        self.client.force_login(armazenista)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_usuario_fabrica_edita(self):
        fabril = User.objects.create_user(
            username='fab', email='fab@coop-a.test', password='x',
            cooperativa=self.cooperativa, papel=User.PAPEL_USUARIO_FABRICA,
        )
        self.client.force_login(fabril)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_admin_vector_recebe_403(self):
        vector = User.objects.create_user(
            username='vec', email='vec@t.test', password='x', papel=User.PAPEL_ADMIN_VECTOR,
        )
        self.client.force_login(vector)
        self.assertEqual(self.client.get(self.url).status_code, 403)
