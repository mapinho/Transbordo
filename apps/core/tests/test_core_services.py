import datetime

from django.test import TestCase

from apps.core import services
from apps.core.models import Cooperativa
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, LogExecucao, MovimentacaoDiaria,
)


class MetricasOrganizacaoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="A", slug="a")
        self.oficial = Cenario.all_cooperativas.create(
            cooperativa=self.coop, nome="Oficial", is_oficial=True,
        )
        self.f = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.oficial, nome="F1",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )
        self.a = Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.oficial, nome="A1",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )

    def test_contagens_e_massa(self):
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.oficial, data=datetime.date(2025, 1, 1),
            armazem=self.a, fabrica=self.f, quantidade_ton=120.0, custo_total=3000.0,
        )
        LogExecucao.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.oficial, status=LogExecucao.Status.SUCESSO,
        )
        m = services.metricas_da_organizacao(self.coop.id)
        self.assertEqual((m["fabricas"], m["armazens"], m["cenarios"]), (1, 1, 1))
        self.assertEqual(m["toneladas"], 120.0)
        self.assertEqual(m["sacas"], 120.0 * 1000 / 60)
        self.assertEqual(m["frete"], 3000.0)
        self.assertIsNotNone(m["ultima_simulacao"])

    def test_sem_execucao_sucesso_ultima_simulacao_none(self):
        m = services.metricas_da_organizacao(self.coop.id)
        self.assertIsNone(m["ultima_simulacao"])
        self.assertEqual(m["toneladas"], 0.0)

    def test_organizacao_sem_cenario_oficial(self):
        coop2 = Cooperativa.objects.create(nome="B", slug="b")
        m = services.metricas_da_organizacao(coop2.id)
        self.assertEqual(m["fabricas"], 0)
        self.assertIsNone(m["toneladas"])


class MetricasConsolidadasTests(TestCase):
    def test_totais_somam_as_linhas(self):
        for nome in ("A", "B"):
            c = Cooperativa.objects.create(nome=nome, slug=nome.lower())
            cen = Cenario.all_cooperativas.create(cooperativa=c, nome="Of", is_oficial=True)
            f = Fabrica.all_cooperativas.create(
                cooperativa=c, cenario=cen, nome="F", capacidade_estatica=1,
                capacidade_esmagamento_diaria=1, capacidade_recebimento_diaria=1,
                limite_caminhoes=1, carga_media_caminhao=1, estoque_inicial=0,
            )
            a = Armazem.all_cooperativas.create(
                cooperativa=c, cenario=cen, nome="A", capacidade_estatica=1,
                capacidade_expedicao_diaria=1, estoque_inicial=0,
            )
            MovimentacaoDiaria.all_cooperativas.create(
                cooperativa=c, cenario=cen, data=datetime.date(2025, 1, 1),
                armazem=a, fabrica=f, quantidade_ton=10.0, custo_total=100.0,
            )
        cons = services.metricas_consolidadas()
        self.assertEqual(cons["totais"]["organizacoes"], 2)
        self.assertEqual(cons["totais"]["toneladas"], 20.0)
        self.assertEqual(cons["totais"]["frete"], 200.0)
        self.assertEqual(len(cons["por_organizacao"]), 2)
