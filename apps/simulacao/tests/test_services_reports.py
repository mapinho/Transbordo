from django.test import TestCase

from apps.core.models import Cooperativa
from apps.simulacao import services
from apps.simulacao.models import Armazem, Cenario, Fabrica, ResumoMensalArmazem, ResumoMensalFabrica


class ReportsFixtureMixin:
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=10000, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=5000, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )


class GetFactoriesSummaryTests(ReportsFixtureMixin, TestCase):
    def test_retorna_resumo_com_nome_da_fabrica(self):
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
            rec_produtor=100, rec_transbordo=50, esmagado=120, saldo_estoque=30,
            capacidade_estatica=10000, excedente=0,
        )

        resultado = services.get_factories_summary(self.cenario.id)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]['fabrica'], 'Fábrica Teste')
        self.assertEqual(resultado[0]['recebimento_produtor_ton'], 100)


class GetWarehousesSummaryTests(ReportsFixtureMixin, TestCase):
    def test_retorna_resumo_com_nome_do_armazem(self):
        ResumoMensalArmazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', armazem=self.armazem,
            rec_produtor=200, envio_transbordo=150, vendas=10, saldo_estoque=40,
            capacidade_estatica=5000, excedente=0,
        )

        resultado = services.get_warehouses_summary(self.cenario.id)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]['armazem'], 'Armazém Teste')
        self.assertEqual(resultado[0]['envio_transbordo_ton'], 150)


class CompareFactoriesTests(ReportsFixtureMixin, TestCase):
    def test_agrega_pico_de_estoque_e_totais(self):
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
            rec_produtor=100, rec_transbordo=0, esmagado=50, saldo_estoque=200,
            capacidade_estatica=10000, excedente=0,
        )
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-02', fabrica=self.fabrica,
            rec_produtor=100, rec_transbordo=0, esmagado=50, saldo_estoque=300,
            capacidade_estatica=10000, excedente=0,
        )

        resultado = services.compare_factories(self.cenario.id)

        self.assertEqual(len(resultado), 1)
        linha = resultado[0]
        self.assertEqual(linha['recebimento_produtor_total_ton'], 200)
        self.assertEqual(linha['pico_estoque_mensal_ton'], 300)

    def test_sem_resumos_retorna_lista_vazia(self):
        self.assertEqual(services.compare_factories(self.cenario.id), [])


class CompareWarehousesTests(ReportsFixtureMixin, TestCase):
    def test_agrega_pico_de_estoque_e_totais(self):
        ResumoMensalArmazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', armazem=self.armazem,
            rec_produtor=100, envio_transbordo=0, vendas=0, saldo_estoque=100,
            capacidade_estatica=5000, excedente=0,
        )
        ResumoMensalArmazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-02', armazem=self.armazem,
            rec_produtor=100, envio_transbordo=0, vendas=0, saldo_estoque=50,
            capacidade_estatica=5000, excedente=0,
        )

        resultado = services.compare_warehouses(self.cenario.id)

        self.assertEqual(len(resultado), 1)
        linha = resultado[0]
        self.assertEqual(linha['recebimento_produtor_total_ton'], 200)
        self.assertEqual(linha['pico_estoque_mensal_ton'], 100)

    def test_sem_resumos_retorna_lista_vazia(self):
        self.assertEqual(services.compare_warehouses(self.cenario.id), [])


class GetStockExcessesReportTests(ReportsFixtureMixin, TestCase):
    def test_detecta_excedente_positivo_em_fabrica_e_armazem(self):
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
            rec_produtor=0, rec_transbordo=0, esmagado=0, saldo_estoque=12000,
            capacidade_estatica=10000, excedente=2000,
        )
        ResumoMensalArmazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', armazem=self.armazem,
            rec_produtor=0, envio_transbordo=0, vendas=0, saldo_estoque=0,
            capacidade_estatica=5000, excedente=0,
        )

        alertas = services.get_stock_excesses_report(self.cenario.id)

        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]['entidade_tipo'], 'Fabrica')
        self.assertEqual(alertas[0]['entidade_nome'], 'Fábrica Teste')
        self.assertEqual(alertas[0]['excedente_estouro_ton'], 2000)


class GetStockRupturesReportTests(ReportsFixtureMixin, TestCase):
    def test_detecta_saldo_negativo(self):
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
            rec_produtor=100, rec_transbordo=0, esmagado=200, saldo_estoque=-50.0,
            capacidade_estatica=10000, excedente=0,
        )

        alertas = services.get_stock_ruptures_report(self.cenario.id)

        self.assertEqual(len(alertas), 1)
        alerta = alertas[0]
        self.assertEqual(alerta['entidade_nome'], 'Fábrica Teste')
        self.assertEqual(alerta['entidade_tipo'], 'Fabrica')
        self.assertAlmostEqual(alerta['deficit_ton'], 50.0)
