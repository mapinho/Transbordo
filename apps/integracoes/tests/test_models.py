from django.db import IntegrityError
from django.test import TestCase

from apps.core.models import Cooperativa
from apps.integracoes.models import ApiKey, gerar_chave


class ApiKeyModelTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')

    def test_chave_gerada_automaticamente_e_unica(self):
        k1 = ApiKey.objects.create(cooperativa=self.cooperativa, nome='Serviço MCP')
        k2 = ApiKey.objects.create(cooperativa=self.cooperativa, nome='Outro serviço')

        self.assertTrue(k1.chave)
        self.assertNotEqual(k1.chave, k2.chave)
        self.assertTrue(k1.ativo)

    def test_chave_duplicada_e_rejeitada(self):
        chave = gerar_chave()
        ApiKey.objects.create(cooperativa=self.cooperativa, nome='A', chave=chave)
        with self.assertRaises(IntegrityError):
            ApiKey.objects.create(cooperativa=self.cooperativa, nome='B', chave=chave)

    def test_str_inclui_nome_e_cooperativa(self):
        k = ApiKey.objects.create(cooperativa=self.cooperativa, nome='Serviço MCP')
        self.assertIn('Serviço MCP', str(k))
        self.assertIn('Coop A', str(k))
