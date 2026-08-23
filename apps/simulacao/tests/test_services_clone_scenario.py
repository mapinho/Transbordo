import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.simulacao import services
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, PrevisaoArmazem, PrevisaoFabrica, Rota, SafraUnidade,
)


class CloneScenarioTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.origem = Cenario.all_cooperativas.create(
            cooperativa=self.cooperativa, nome='Oficial', is_oficial=True,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.origem, nome='Fábrica 1',
            capacidade_estatica=1000, capacidade_esmagamento_diaria=100,
            capacidade_recebimento_diaria=100, limite_caminhoes=10,
            carga_media_caminhao=30, estoque_inicial=500,
        )
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.origem, nome='Armazém 1',
            capacidade_estatica=800, capacidade_expedicao_diaria=50, estoque_inicial=200,
        )
        Rota.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.origem,
            armazem=self.armazem, fabrica=self.fabrica,
            distancia_km=120, custo_frete_ton=45, custo_frete_entressafra=30,
        )
        PrevisaoFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, fabrica=self.fabrica,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=300, vendas=100,
        )
        PrevisaoArmazem.all_cooperativas.create(
            cooperativa=self.cooperativa, armazem=self.armazem,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=200, vendas=50,
        )
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.origem,
            entidade_tipo='Armazém', entidade_id=self.armazem.id,
            data_inicio=datetime.date(2026, 1, 15), data_fim=datetime.date(2026, 4, 15),
        )

    def test_clona_fabricas_armazens_rotas_previsoes_e_safras(self):
        novo_id = services.clone_scenario(self.cooperativa.id, 'Simulação 1', self.origem.id)

        novo = Cenario.all_cooperativas.get(id=novo_id)
        self.assertEqual(novo.nome, 'Simulação 1')
        self.assertFalse(novo.is_oficial)

        fabricas = list(Fabrica.all_cooperativas.filter(cenario_id=novo_id))
        self.assertEqual(len(fabricas), 1)
        self.assertEqual(fabricas[0].nome, 'Fábrica 1')
        self.assertNotEqual(fabricas[0].id, self.fabrica.id)

        armazens = list(Armazem.all_cooperativas.filter(cenario_id=novo_id))
        self.assertEqual(len(armazens), 1)

        rotas = list(Rota.all_cooperativas.filter(cenario_id=novo_id))
        self.assertEqual(len(rotas), 1)
        self.assertEqual(rotas[0].armazem_id, armazens[0].id)
        self.assertEqual(rotas[0].fabrica_id, fabricas[0].id)

        previsoes_fab = list(PrevisaoFabrica.all_cooperativas.filter(fabrica_id=fabricas[0].id))
        self.assertEqual(len(previsoes_fab), 1)
        self.assertEqual(previsoes_fab[0].recebimento_produtor, 300)

        previsoes_arm = list(PrevisaoArmazem.all_cooperativas.filter(armazem_id=armazens[0].id))
        self.assertEqual(len(previsoes_arm), 1)

        safras = list(SafraUnidade.all_cooperativas.filter(cenario_id=novo_id))
        self.assertEqual(len(safras), 1)
        self.assertEqual(safras[0].entidade_id, armazens[0].id)

    def test_rejeita_cenario_de_origem_de_outra_cooperativa(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')

        with self.assertRaises(ValueError):
            services.clone_scenario(outra_cooperativa.id, 'Simulação 1', self.origem.id)

        self.assertEqual(Cenario.all_cooperativas.filter(cooperativa=outra_cooperativa).count(), 0)

    def test_nome_duplicado_na_mesma_cooperativa_falha(self):
        services.clone_scenario(self.cooperativa.id, 'Simulação 1', self.origem.id)

        with self.assertRaises(Exception):
            services.clone_scenario(self.cooperativa.id, 'Simulação 1', self.origem.id)
