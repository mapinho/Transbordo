from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao.models import Armazem, Cenario, Fabrica, Rota


class CenarioTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')

    def test_criacao_com_campos_minimos(self):
        cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')

        self.assertFalse(cenario.is_oficial)
        self.assertIsNotNone(cenario.data_criacao)

    def test_str_retorna_nome(self):
        cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')

        self.assertEqual(str(cenario), 'Cenário Teste')


class FabricaTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')

    def _fabrica_valida(self, **overrides):
        dados = dict(
            cooperativa=self.cooperativa,
            cenario=self.cenario,
            nome='Fábrica Teste',
            capacidade_estatica=10000,
            capacidade_esmagamento_diaria=500,
            capacidade_recebimento_diaria=600,
            limite_caminhoes=20,
            carga_media_caminhao=30,
            estoque_inicial=1000,
        )
        dados.update(overrides)
        return Fabrica(**dados)

    def test_criacao_com_campos_validos(self):
        fabrica = self._fabrica_valida()
        fabrica.full_clean()
        fabrica.save()

        self.assertEqual(fabrica.cenario_id, self.cenario.id)

    def test_clean_rejeita_cooperativa_diferente_da_do_cenario(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        fabrica = self._fabrica_valida(cooperativa=outra_cooperativa)

        with self.assertRaises(ValidationError):
            fabrica.full_clean()


class TenantIsolationRealModelsTests(TestCase):
    """Formal isolation proof against real, concrete models (not the throwaway
    Item from the Fundação plan's test_tenancy.py) -- required by the spec's
    'testes de isolamento de tenant' for this phase."""

    def setUp(self):
        self.coop_a = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        self.cenario_a = Cenario.all_cooperativas.create(cooperativa=self.coop_a, nome='Cenário A')
        self.cenario_b = Cenario.all_cooperativas.create(cooperativa=self.coop_b, nome='Cenário B')
        Fabrica.all_cooperativas.create(
            cooperativa=self.coop_a, cenario=self.cenario_a, nome='Fábrica A',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )
        Fabrica.all_cooperativas.create(
            cooperativa=self.coop_b, cenario=self.cenario_b, nome='Fábrica B',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def test_objects_manager_never_leaks_other_cooperativa(self):
        token = definir_cooperativa_atual(self.coop_a.id)
        try:
            nomes = list(Fabrica.objects.values_list('nome', flat=True))
            cenarios = list(Cenario.objects.values_list('nome', flat=True))
        finally:
            resetar_cooperativa_atual(token)

        self.assertEqual(nomes, ['Fábrica A'])
        self.assertEqual(cenarios, ['Cenário A'])

    def test_all_cooperativas_manager_sees_both(self):
        self.assertEqual(Fabrica.all_cooperativas.count(), 2)
        self.assertEqual(Cenario.all_cooperativas.count(), 2)
