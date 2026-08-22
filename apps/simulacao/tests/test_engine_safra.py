import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.simulacao import engine
from apps.simulacao.models import Armazem, Cenario, SafraUnidade


class JanelaSafraDeRegistroTests(TestCase):
    def test_sem_registro_fallback_varia_por_ano(self):
        na_safra_2026, ini_2026, fim_2026 = engine._janela_safra_de_registro(None, datetime.date(2026, 2, 1))
        na_safra_2027, ini_2027, fim_2027 = engine._janela_safra_de_registro(None, datetime.date(2027, 2, 1))

        self.assertEqual((ini_2026, fim_2026), (datetime.date(2026, 1, 15), datetime.date(2026, 4, 15)))
        self.assertEqual((ini_2027, fim_2027), (datetime.date(2027, 1, 15), datetime.date(2027, 4, 15)))
        self.assertTrue(na_safra_2026)
        self.assertTrue(na_safra_2027)

    def test_com_registro_usa_datas_do_registro(self):
        cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        cenario = Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='Cenário Teste')
        safra = SafraUnidade.all_cooperativas.create(
            cooperativa=cooperativa, cenario=cenario, entidade_tipo='Armazém', entidade_id=1,
            data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
        )

        na_safra, ini, fim = engine._janela_safra_de_registro(safra, datetime.date(2026, 2, 15))

        self.assertTrue(na_safra)
        self.assertEqual((ini, fim), (datetime.date(2026, 2, 1), datetime.date(2026, 3, 1)))


class ObterJanelaSafraTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )

    def test_com_registro_data_dentro(self):
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, entidade_tipo='Armazém',
            entidade_id=self.armazem.id,
            data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
        )

        na_safra, d_ini, d_fim = engine.obter_janela_safra(
            'Armazém', self.armazem.id, datetime.date(2026, 2, 15), self.cenario.id
        )

        self.assertTrue(na_safra)
        self.assertEqual((d_ini, d_fim), (datetime.date(2026, 2, 1), datetime.date(2026, 3, 1)))

    def test_com_registro_data_fora(self):
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, entidade_tipo='Armazém',
            entidade_id=self.armazem.id,
            data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
        )

        na_safra, d_ini, d_fim = engine.obter_janela_safra(
            'Armazém', self.armazem.id, datetime.date(2026, 3, 15), self.cenario.id
        )

        self.assertFalse(na_safra)
        self.assertEqual((d_ini, d_fim), (datetime.date(2026, 2, 1), datetime.date(2026, 3, 1)))

    def test_sem_registro_usa_padrao_15jan_15abr(self):
        na_safra_dentro, d_ini, d_fim = engine.obter_janela_safra(
            'Armazém', self.armazem.id, datetime.date(2026, 2, 1), self.cenario.id
        )
        self.assertEqual((d_ini, d_fim), (datetime.date(2026, 1, 15), datetime.date(2026, 4, 15)))
        self.assertTrue(na_safra_dentro)

        na_safra_fora, d_ini2, d_fim2 = engine.obter_janela_safra(
            'Armazém', self.armazem.id, datetime.date(2026, 5, 1), self.cenario.id
        )
        self.assertEqual((d_ini2, d_fim2), (datetime.date(2026, 1, 15), datetime.date(2026, 4, 15)))
        self.assertFalse(na_safra_fora)
