import io

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario, Fabrica
from apps.simulacao.planilha import ABA_ARMAZENS, ABA_FABRICAS, analisar
from apps.simulacao.tests.planilha_fixtures import montar_pasta, montar_pasta_bruta

FABRICA_OK = {
    'nome': 'FÁBRICA TESTE',
    'capacidade_estatica': 50000,
    'capacidade_esmagamento_diaria': 1200,
    'capacidade_recebimento_diaria': 2000,
    'limite_caminhoes': 60,
    'carga_media_caminhao': 36,
    'estoque_inicial': 8000,
}

ARMAZEM_OK = {
    'nome': 'ARMAZÉM A',
    'capacidade_estatica': 30000,
    'capacidade_expedicao_diaria': 900,
    'estoque_inicial': 12000,
}


class AnalisarEstruturaTests(TestCase):
    def test_arquivo_ilegivel_e_erro_estrutural(self):
        relatorio = analisar(io.BytesIO(b'isto nao e um xlsx'), None)

        self.assertTrue(relatorio.tem_erro_estrutural)
        self.assertIn('xlsx', relatorio.erro_estrutural.lower())

    def test_pasta_sem_nenhuma_aba_reconhecida_e_erro_estrutural(self):
        pasta = montar_pasta_bruta({'Planilha1': [['a', 'b'], [1, 2]]})

        relatorio = analisar(pasta, None)

        self.assertTrue(relatorio.tem_erro_estrutural)

    def test_aba_com_cabecalho_irreconhecivel_e_erro_estrutural(self):
        pasta = montar_pasta_bruta({ABA_FABRICAS: [['coluna_inventada'], ['x']]})

        relatorio = analisar(pasta, None)

        self.assertTrue(relatorio.tem_erro_estrutural)
        self.assertIn(ABA_FABRICAS, relatorio.erro_estrutural)

    def test_aba_ausente_nao_e_erro(self):
        """Uma pasta só com Fábricas é válida -- as demais abas ficam vazias."""
        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK]), None)

        self.assertFalse(relatorio.tem_erro_estrutural)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_ARMAZENS).criar, 0)

    def test_cabecalho_e_normalizado(self):
        linha = {k.upper() + '  ': v for k, v in FABRICA_OK.items()}

        relatorio = analisar(montar_pasta(fabricas=[linha]), None)

        self.assertFalse(relatorio.tem_erro_estrutural)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 1)


class AnalisarFabricasArmazensTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Comigo', slug='comigo')
        self.cenario = Cenario.all_cooperativas.create(
            cooperativa=self.coop, nome='Oficial', is_oficial=True,
        )

    def test_cenario_none_conta_tudo_como_criacao(self):
        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK]), None)

        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).atualizar, 0)
        self.assertEqual(relatorio.resumo(ABA_ARMAZENS).criar, 1)

    def test_nome_ja_existente_no_cenario_conta_como_atualizacao(self):
        Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='FÁBRICA TESTE',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK]), self.cenario)

        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 0)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).atualizar, 1)

    def test_campo_numerico_em_branco_rejeita_a_linha_e_nomeia_a_coluna(self):
        ruim = dict(FABRICA_OK, nome='SEM CAPACIDADE', capacidade_estatica=None)

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK, ruim]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 1)
        self.assertEqual(len(resumo.rejeitadas), 1)
        rejeitada = resumo.rejeitadas[0]
        self.assertIn('capacidade_estatica', rejeitada.motivo)
        self.assertEqual(rejeitada.valores['nome'], 'SEM CAPACIDADE')

    def test_numero_da_linha_e_o_do_excel(self):
        """Cabeçalho é a linha 1, então a segunda linha de dados é a 3."""
        ruim = dict(FABRICA_OK, nome='RUIM', estoque_inicial=None)

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK, ruim]), None)

        self.assertEqual(relatorio.resumo(ABA_FABRICAS).rejeitadas[0].linha, 3)

    def test_valor_nao_numerico_rejeita_a_linha(self):
        ruim = dict(FABRICA_OK, nome='TEXTO NO NUMERO', limite_caminhoes='muitos')

        relatorio = analisar(montar_pasta(fabricas=[ruim]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 0)
        self.assertIn('limite_caminhoes', resumo.rejeitadas[0].motivo)

    def test_nome_em_branco_rejeita_a_linha(self):
        relatorio = analisar(montar_pasta(fabricas=[dict(FABRICA_OK, nome=None)]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 0)
        self.assertIn('nome', resumo.rejeitadas[0].motivo)

    def test_linha_ruim_nao_aborta_a_aba(self):
        outra = dict(FABRICA_OK, nome='OUTRA FÁBRICA')
        ruim = dict(FABRICA_OK, nome='RUIM', carga_media_caminhao=None)

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK, ruim, outra]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 2)
        self.assertEqual(len(resumo.rejeitadas), 1)

    def test_analisar_nao_escreve_nada(self):
        """A garantia que sustenta a pré-visualização."""
        antes = (Fabrica.all_cooperativas.count(), Armazem.all_cooperativas.count())

        analisar(montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK]), self.cenario)

        depois = (Fabrica.all_cooperativas.count(), Armazem.all_cooperativas.count())
        self.assertEqual(antes, depois)

    def test_nome_duplicado_na_mesma_aba_rejeita_segunda_ocorrencia(self):
        """Duas linhas com o mesmo nome na mesma aba: primeira é criação, segunda é rejeitada."""
        duplicada = dict(FABRICA_OK, nome='FÁBRICA TESTE')  # mesmo nome de FABRICA_OK
        outra = dict(FABRICA_OK, nome='OUTRA FÁBRICA')

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK, duplicada, outra]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 2)  # FÁBRICA TESTE e OUTRA FÁBRICA
        self.assertEqual(len(resumo.rejeitadas), 1)
        rejeitada = resumo.rejeitadas[0]
        self.assertIn('duplicado', rejeitada.motivo)
        self.assertEqual(rejeitada.linha, 3)  # segunda linha de dados = Excel row 3

    def test_mesmo_nome_em_abas_diferentes_nao_e_duplicado(self):
        """Mesmo nome em Fábricas e Armazéns é válido -- são entidades diferentes."""
        fabrica = dict(FABRICA_OK, nome='ENTIDADE COMPARTILHADA')
        armazem = dict(ARMAZEM_OK, nome='ENTIDADE COMPARTILHADA')

        relatorio = analisar(montar_pasta(fabricas=[fabrica], armazens=[armazem]), None)

        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).atualizar, 0)
        self.assertEqual(len(relatorio.resumo(ABA_FABRICAS).rejeitadas), 0)
        self.assertEqual(relatorio.resumo(ABA_ARMAZENS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_ARMAZENS).atualizar, 0)
        self.assertEqual(len(relatorio.resumo(ABA_ARMAZENS).rejeitadas), 0)
