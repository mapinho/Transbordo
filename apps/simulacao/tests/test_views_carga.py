import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Cooperativa, User
from apps.simulacao.models import Cenario, Fabrica
from apps.simulacao.planilha import ABAS_NA_ORDEM
from apps.simulacao.tests.planilha_fixtures import montar_pasta
from apps.simulacao.tests.test_planilha_analisar import ARMAZEM_OK, FABRICA_OK

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def upload(nome='dados.xlsx', **abas):
    if not abas:
        abas = {'fabricas': [FABRICA_OK], 'armazens': [ARMAZEM_OK]}
    return SimpleUploadedFile(nome, montar_pasta(**abas).read(), content_type=XLSX)


class CargaTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Uploads de carga vao para MEDIA_ROOT/carga/<token>.xlsx; sem isolar
        # aqui, uma pre-visualizacao que nao e confirmada (varios testes deste
        # arquivo fazem isso de proposito) deixa .xlsx real em media/carga/ a
        # cada execucao da suite.
        cls._media_root = tempfile.TemporaryDirectory()
        cls._media_root_override = override_settings(MEDIA_ROOT=cls._media_root.name)
        cls._media_root_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_root_override.disable()
        cls._media_root.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Comigo', slug='comigo')
        self.user = User.objects.create_user(
            username='teste', password='segredo123',
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop,
        )
        self.client.force_login(self.user)

    def test_exige_login(self):
        self.client.logout()

        resposta = self.client.get(reverse('simulacao:carga'))

        self.assertEqual(resposta.status_code, 302)

    def test_template_e_servido_como_xlsx(self):
        resposta = self.client.get(reverse('simulacao:carga_template'))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta['Content-Type'], XLSX)
        self.assertIn('attachment', resposta['Content-Disposition'])

    def test_upload_para_cenario_novo_mostra_previsao_sem_escrever(self):
        resposta = self.client.post(
            reverse('simulacao:carga'),
            {'nome_novo': 'Oficial 2026', 'arquivo': upload()}, follow=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Oficial 2026')
        self.assertFalse(Cenario.all_cooperativas.exists())
        self.assertFalse(Fabrica.all_cooperativas.exists())

    def test_confirmar_grava_e_cria_o_cenario_oficial(self):
        self.client.post(
            reverse('simulacao:carga'),
            {'nome_novo': 'Oficial 2026', 'arquivo': upload()}, follow=True,
        )
        token = self.client.session['carga']['token']

        self.client.post(reverse('simulacao:carga_preview', args=[token]), follow=True)

        cenario = Cenario.all_cooperativas.get(nome='Oficial 2026')
        self.assertTrue(cenario.is_oficial)
        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 1)

    def test_upload_para_cenario_existente(self):
        cenario = Cenario.all_cooperativas.create(
            cooperativa=self.coop, nome='Oficial', is_oficial=True,
        )
        self.client.post(
            reverse('simulacao:carga'),
            {'cenario_id': cenario.id, 'arquivo': upload()}, follow=True,
        )
        token = self.client.session['carga']['token']

        self.client.post(reverse('simulacao:carga_preview', args=[token]), follow=True)

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(Cenario.all_cooperativas.count(), 1)

    def test_cenario_de_outra_cooperativa_nao_e_alcancavel(self):
        outra = Cooperativa.objects.create(nome='Outra', slug='outra')
        alheio = Cenario.all_cooperativas.create(
            cooperativa=outra, nome='Alheio', is_oficial=True,
        )

        resposta = self.client.post(
            reverse('simulacao:carga'), {'cenario_id': alheio.id, 'arquivo': upload()},
        )

        self.assertEqual(resposta.status_code, 404)
        self.assertFalse(Fabrica.all_cooperativas.exists())

    def test_arquivo_ilegivel_mostra_erro_estrutural_e_nao_oferece_confirmar(self):
        ruim = SimpleUploadedFile('x.xlsx', b'nao e um xlsx', content_type=XLSX)

        resposta = self.client.post(
            reverse('simulacao:carga'), {'nome_novo': 'Qualquer', 'arquivo': ruim}, follow=True,
        )

        self.assertContains(resposta, 'xlsx')
        self.assertNotContains(resposta, 'name="confirmar"')

    def test_preview_de_token_alheio_e_404(self):
        self.client.post(
            reverse('simulacao:carga'),
            {'nome_novo': 'Oficial', 'arquivo': upload()}, follow=True,
        )

        resposta = self.client.get(
            reverse('simulacao:carga_preview', args=['token-inventado'])
        )

        self.assertEqual(resposta.status_code, 404)

    def test_previsao_lista_as_linhas_rejeitadas(self):
        ruim = upload(
            fabricas=[FABRICA_OK, dict(FABRICA_OK, nome='RUIM', estoque_inicial=None)]
        )

        resposta = self.client.post(
            reverse('simulacao:carga'), {'nome_novo': 'Oficial', 'arquivo': ruim}, follow=True,
        )

        self.assertContains(resposta, 'estoque_inicial')

    def test_pagina_de_upload_lista_as_cinco_abas_esperadas(self):
        resposta = self.client.get(reverse('simulacao:carga'))

        for nome in ABAS_NA_ORDEM:
            self.assertContains(resposta, nome)

    def test_confirmar_nome_de_cenario_duplicado_nao_derruba_com_500(self):
        self.client.post(
            reverse('simulacao:carga'),
            {'nome_novo': 'Oficial 2026', 'arquivo': upload()}, follow=True,
        )
        token1 = self.client.session['carga']['token']
        self.client.post(reverse('simulacao:carga_preview', args=[token1]), follow=True)

        self.client.post(
            reverse('simulacao:carga'),
            {'nome_novo': 'Oficial 2026', 'arquivo': upload()}, follow=True,
        )
        token2 = self.client.session['carga']['token']

        resposta = self.client.post(reverse('simulacao:carga_preview', args=[token2]))

        self.assertEqual(resposta.status_code, 400)
        self.assertContains(resposta, 'Oficial 2026', status_code=400)
