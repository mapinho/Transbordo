import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao.models import Armazem, Cenario, Fabrica, Rota, MovimentacaoDiaria, PrevisaoArmazem, PrevisaoFabrica, SafraUnidade, LogExecucao, ResumoMensalArmazem, ResumoMensalFabrica


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

    def test_duas_cooperativas_podem_ter_cenario_com_mesmo_nome(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Baseline')

        cenario_outra_coop = Cenario.all_cooperativas.create(
            cooperativa=outra_cooperativa, nome='Baseline'
        )

        self.assertEqual(cenario_outra_coop.nome, 'Baseline')

    def test_mesma_cooperativa_nao_pode_ter_dois_cenarios_com_mesmo_nome(self):
        Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Baseline')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Baseline')


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


class PrevisaoFabricaTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def test_criacao_com_campos_validos(self):
        previsao = PrevisaoFabrica(
            cooperativa=self.cooperativa, fabrica=self.fabrica,
            mes_referencia=datetime.date(2026, 1, 1),
            recebimento_produtor=100, vendas=50,
        )
        previsao.full_clean()
        previsao.save()

        self.assertEqual(previsao.fabrica_id, self.fabrica.id)

    def test_clean_rejeita_cooperativa_diferente_da_da_fabrica(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        previsao = PrevisaoFabrica(
            cooperativa=outra_cooperativa, fabrica=self.fabrica,
            mes_referencia=datetime.date(2026, 1, 1),
        )

        with self.assertRaises(ValidationError):
            previsao.full_clean()


class PrevisaoArmazemTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )

    def test_criacao_com_campos_validos(self):
        previsao = PrevisaoArmazem(
            cooperativa=self.cooperativa, armazem=self.armazem,
            mes_referencia=datetime.date(2026, 1, 1),
            recebimento_produtor=100, vendas=50,
        )
        previsao.full_clean()
        previsao.save()

        self.assertEqual(previsao.armazem_id, self.armazem.id)

    def test_clean_rejeita_cooperativa_diferente_da_do_armazem(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        previsao = PrevisaoArmazem(
            cooperativa=outra_cooperativa, armazem=self.armazem,
            mes_referencia=datetime.date(2026, 1, 1),
        )

        with self.assertRaises(ValidationError):
            previsao.full_clean()


class SafraUnidadeTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')

    def test_criacao_com_campos_validos(self):
        safra = SafraUnidade(
            cooperativa=self.cooperativa, cenario=self.cenario,
            entidade_tipo='Armazém', entidade_id=1,
            data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
        )
        safra.full_clean()
        safra.save()

        self.assertEqual(safra.entidade_tipo, 'Armazém')


class MovimentacaoDiariaTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def test_criacao_com_campos_validos(self):
        mov = MovimentacaoDiaria(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 1), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=10.5, custo_total=210.0,
        )
        mov.full_clean()
        mov.save()

        self.assertEqual(mov.quantidade_ton, 10.5)


class LogExecucaoTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')

    def test_criacao_com_cenario(self):
        log = LogExecucao(
            cooperativa=self.cooperativa, cenario=self.cenario,
            status='sucesso', mensagem='ok', duracao_segundos=1.5, dias_simulados=7,
        )
        log.full_clean()
        log.save()

        self.assertEqual(log.cenario_id, self.cenario.id)

    def test_criacao_sem_cenario_e_valida(self):
        """cenario=None representa execução contra o cenário oficial (ver ADR 0005)."""
        log = LogExecucao(
            cooperativa=self.cooperativa, cenario=None,
            status='sucesso', mensagem='ok', duracao_segundos=1.5, dias_simulados=7,
        )
        log.full_clean()
        log.save()

        self.assertIsNone(log.cenario_id)

    def test_clean_rejeita_cooperativa_diferente_da_do_cenario_quando_presente(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        log = LogExecucao(cooperativa=outra_cooperativa, cenario=self.cenario, status='sucesso')

        with self.assertRaises(ValidationError):
            log.full_clean()


class ResumoMensalFabricaTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def test_criacao_com_campos_validos(self):
        resumo = ResumoMensalFabrica(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
        )
        resumo.full_clean()
        resumo.save()

        self.assertEqual(resumo.rec_produtor, 0)


class ResumoMensalArmazemTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )

    def test_criacao_com_campos_validos(self):
        resumo = ResumoMensalArmazem(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', armazem=self.armazem,
        )
        resumo.full_clean()
        resumo.save()

        self.assertEqual(resumo.rec_produtor, 0)
