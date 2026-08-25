import datetime

from django.test import SimpleTestCase
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models as legado
from apps.simulacao.legado import ler_legado


class LerLegadoTests(SimpleTestCase):
    """Exercita ler_legado contra um SQLite em memória construído a partir
    do metadata do ORM legado -- mesmo padrão de tests/conftest.py. Não toca
    no banco Django, por isso SimpleTestCase."""

    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        legado.Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

        cenario = legado.Cenario(
            nome='Oficial (Planejado)',
            is_oficial=True,
            data_criacao=datetime.datetime(2026, 6, 1, 14, 19, 30),
        )
        self.session.add(cenario)
        self.session.flush()

        fabrica = legado.Fabrica(
            cenario_id=cenario.id, nome='FÁBRICA RIO VERDE',
            capacidade_estatica=50000, capacidade_esmagamento_diaria=1200,
            capacidade_recebimento_diaria=2000, limite_caminhoes=60,
            carga_media_caminhao=36, estoque_inicial=8000,
        )
        armazem = legado.Armazem(
            cenario_id=cenario.id, nome='JATAÍ',
            capacidade_estatica=30000, capacidade_expedicao_diaria=900,
            estoque_inicial=12000,
        )
        self.session.add_all([fabrica, armazem])
        self.session.flush()

        self.session.add_all([
            legado.Rota(
                cenario_id=cenario.id, armazem_id=armazem.id, fabrica_id=fabrica.id,
                distancia_km=118.5, custo_frete_ton=42.75, custo_frete_entressafra=38.0,
            ),
            legado.PrevisaoFabrica(
                fabrica_id=fabrica.id, mes_referencia=datetime.date(2026, 3, 1),
                recebimento_produtor=4500.5, vendas=1200.25,
            ),
            legado.PrevisaoArmazem(
                armazem_id=armazem.id, mes_referencia=datetime.date(2026, 3, 1),
                recebimento_produtor=7800.0, vendas=300.0,
            ),
            legado.SafraUnidade(
                cenario_id=cenario.id, entidade_tipo='Armazém', entidade_id=armazem.id,
                data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 5, 31),
            ),
        ])
        self.session.commit()

        self.cenario_id = cenario.id
        self.fabrica_id = fabrica.id
        self.armazem_id = armazem.id

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_le_as_sete_tabelas_de_entrada(self):
        dados = ler_legado(self.session)

        self.assertEqual(len(dados.cenarios), 1)
        self.assertEqual(len(dados.fabricas), 1)
        self.assertEqual(len(dados.armazens), 1)
        self.assertEqual(len(dados.rotas), 1)
        self.assertEqual(len(dados.previsoes_fabrica), 1)
        self.assertEqual(len(dados.previsoes_armazem), 1)
        self.assertEqual(len(dados.safras), 1)

    def test_cenario_carrega_todos_os_campos(self):
        dados = ler_legado(self.session)

        self.assertEqual(dados.cenarios[0], {
            'id': self.cenario_id,
            'nome': 'Oficial (Planejado)',
            'is_oficial': True,
            'data_criacao': datetime.datetime(2026, 6, 1, 14, 19, 30),
        })

    def test_fabrica_e_armazem_carregam_o_cenario_de_origem(self):
        dados = ler_legado(self.session)

        self.assertEqual(dados.fabricas[0]['cenario_id'], self.cenario_id)
        self.assertEqual(dados.fabricas[0]['nome'], 'FÁBRICA RIO VERDE')
        self.assertEqual(dados.fabricas[0]['limite_caminhoes'], 60)
        self.assertEqual(dados.armazens[0]['cenario_id'], self.cenario_id)
        self.assertEqual(dados.armazens[0]['nome'], 'JATAÍ')
        self.assertEqual(dados.armazens[0]['capacidade_expedicao_diaria'], 900)

    def test_rota_referencia_fabrica_e_armazem_pelo_id_legado(self):
        dados = ler_legado(self.session)

        self.assertEqual(dados.rotas[0]['armazem_id'], self.armazem_id)
        self.assertEqual(dados.rotas[0]['fabrica_id'], self.fabrica_id)
        self.assertEqual(dados.rotas[0]['custo_frete_entressafra'], 38.0)

    def test_previsoes_nao_carregam_cenario_id(self):
        """previsoes_fabrica/previsoes_armazem genuinamente não têm essa coluna
        no schema legado -- o escopo por cenário vem da fábrica/armazém."""
        dados = ler_legado(self.session)

        self.assertNotIn('cenario_id', dados.previsoes_fabrica[0])
        self.assertNotIn('cenario_id', dados.previsoes_armazem[0])
        self.assertEqual(dados.previsoes_fabrica[0]['fabrica_id'], self.fabrica_id)
        self.assertEqual(dados.previsoes_armazem[0]['armazem_id'], self.armazem_id)

    def test_safra_carrega_tipo_e_entidade(self):
        dados = ler_legado(self.session)

        self.assertEqual(dados.safras[0]['entidade_tipo'], 'Armazém')
        self.assertEqual(dados.safras[0]['entidade_id'], self.armazem_id)
        self.assertEqual(dados.safras[0]['data_inicio'], datetime.date(2026, 2, 1))
