from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import obter_cooperativa_atual
from apps.integracoes.models import ApiKey


class ApiKeyAuthTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.api_key = ApiKey.objects.create(cooperativa=self.cooperativa, nome='Serviço MCP')
        self.url = '/api/v1/cenarios/'

    def test_sem_header_retorna_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_chave_inexistente_retorna_401(self):
        response = self.client.get(self.url, headers={'X-API-Key': 'nao-existe'})
        self.assertEqual(response.status_code, 401)

    def test_chave_inativa_retorna_401(self):
        self.api_key.ativo = False
        self.api_key.save(update_fields=['ativo'])
        response = self.client.get(self.url, headers={'X-API-Key': self.api_key.chave})
        self.assertEqual(response.status_code, 401)

    def test_chave_valida_retorna_200(self):
        response = self.client.get(self.url, headers={'X-API-Key': self.api_key.chave})
        self.assertEqual(response.status_code, 200)

    def test_contextvar_de_tenant_limpo_apos_o_request(self):
        self.client.get(self.url, headers={'X-API-Key': self.api_key.chave})
        # CooperativaScopeMiddleware.finally deve ter resetado o contextvar
        self.assertIsNone(obter_cooperativa_atual())
