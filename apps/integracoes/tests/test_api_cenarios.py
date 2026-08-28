from django.test import TestCase

from apps.core.models import Cooperativa
from apps.integracoes.models import ApiKey
from apps.simulacao.models import Cenario


class ListarCenariosTests(TestCase):
    def setUp(self):
        self.coop_a = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.key_a = ApiKey.objects.create(cooperativa=self.coop_a, nome='Serviço A')
        self.cenario_a = Cenario.all_cooperativas.create(
            cooperativa=self.coop_a, nome='Safra 25/26', is_oficial=True,
        )

    def _get(self, key):
        return self.client.get('/api/v1/cenarios/', headers={'X-API-Key': key.chave})

    def test_retorna_cenarios_da_cooperativa_da_chave(self):
        response = self._get(self.key_a)

        self.assertEqual(response.status_code, 200)
        corpo = response.json()
        self.assertEqual(len(corpo), 1)
        self.assertEqual(corpo[0]['nome'], 'Safra 25/26')
        self.assertEqual(corpo[0]['is_oficial'], True)
        self.assertEqual(set(corpo[0].keys()), {'id', 'nome', 'is_oficial', 'data_criacao'})

    def test_isolamento_cross_cooperativa(self):
        coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        key_b = ApiKey.objects.create(cooperativa=coop_b, nome='Serviço B')
        Cenario.all_cooperativas.create(cooperativa=coop_b, nome='Safra 25/26', is_oficial=True)

        corpo_a = self._get(self.key_a).json()
        corpo_b = self._get(key_b).json()

        self.assertEqual([c['nome'] for c in corpo_a], ['Safra 25/26'])
        self.assertEqual([c['nome'] for c in corpo_b], ['Safra 25/26'])
        # mesmo nome, ids distintos — A nunca vê o cenário de B
        self.assertNotEqual(corpo_a[0]['id'], corpo_b[0]['id'])
