import datetime
import warnings

from django.test import TestCase
from django.utils import timezone

from apps.core.models import Cooperativa
from apps.simulacao.legado import DadosLegado, escrever
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, PrevisaoArmazem, PrevisaoFabrica, Rota, SafraUnidade,
)


def dados_de_exemplo():
    """Dois cenários, cada um com 1 fábrica + 1 armazém + 1 rota + previsões
    + 1 safra. Os IDs legados são deliberadamente altos e esparsos para que
    um remapeamento faltante fique evidente."""
    return DadosLegado(
        cenarios=[
            {'id': 6, 'nome': 'Oficial (Planejado)', 'is_oficial': True,
             'data_criacao': datetime.datetime(2026, 6, 1, 14, 19, 30)},
            {'id': 7, 'nome': 'Replanejado com Vendas', 'is_oficial': False,
             'data_criacao': datetime.datetime(2026, 6, 3, 13, 32, 48)},
        ],
        fabricas=[
            {'id': 101, 'cenario_id': 6, 'nome': 'FÁBRICA RIO VERDE',
             'capacidade_estatica': 50000, 'capacidade_esmagamento_diaria': 1200,
             'capacidade_recebimento_diaria': 2000, 'limite_caminhoes': 60,
             'carga_media_caminhao': 36, 'estoque_inicial': 8000},
            {'id': 102, 'cenario_id': 7, 'nome': 'FÁBRICA RIO VERDE',
             'capacidade_estatica': 50000, 'capacidade_esmagamento_diaria': 1200,
             'capacidade_recebimento_diaria': 2000, 'limite_caminhoes': 60,
             'carga_media_caminhao': 36, 'estoque_inicial': 8000},
        ],
        armazens=[
            {'id': 201, 'cenario_id': 6, 'nome': 'JATAÍ', 'capacidade_estatica': 30000,
             'capacidade_expedicao_diaria': 900, 'estoque_inicial': 12000},
            {'id': 202, 'cenario_id': 7, 'nome': 'JATAÍ', 'capacidade_estatica': 30000,
             'capacidade_expedicao_diaria': 900, 'estoque_inicial': 12000},
        ],
        rotas=[
            {'cenario_id': 6, 'armazem_id': 201, 'fabrica_id': 101,
             'distancia_km': 118.5, 'custo_frete_ton': 42.75, 'custo_frete_entressafra': 38.0},
            {'cenario_id': 7, 'armazem_id': 202, 'fabrica_id': 102,
             'distancia_km': 118.5, 'custo_frete_ton': 44.0, 'custo_frete_entressafra': 38.0},
        ],
        previsoes_fabrica=[
            {'fabrica_id': 101, 'mes_referencia': datetime.date(2026, 3, 1),
             'recebimento_produtor': 4500.5, 'vendas': 1200.25},
            {'fabrica_id': 102, 'mes_referencia': datetime.date(2026, 3, 1),
             'recebimento_produtor': 4500.5, 'vendas': 1800.0},
        ],
        previsoes_armazem=[
            {'armazem_id': 201, 'mes_referencia': datetime.date(2026, 3, 1),
             'recebimento_produtor': 7800.0, 'vendas': 300.0},
        ],
        safras=[
            {'cenario_id': 6, 'entidade_tipo': 'Armazém', 'entidade_id': 201,
             'data_inicio': datetime.date(2026, 2, 1), 'data_fim': datetime.date(2026, 5, 31)},
            {'cenario_id': 6, 'entidade_tipo': 'Fábrica', 'entidade_id': 101,
             'data_inicio': datetime.date(2026, 2, 15), 'data_fim': datetime.date(2026, 6, 15)},
        ],
    )


class EscreverTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Comigo', slug='comigo')

    def test_contagens_retornadas_batem_com_a_entrada(self):
        contagens = escrever(dados_de_exemplo(), self.coop)

        self.assertEqual(contagens, {
            'cenarios': 2, 'fabricas': 2, 'armazens': 2, 'rotas': 2,
            'previsoes_fabrica': 2, 'previsoes_armazem': 1, 'safras': 2,
        })

    def test_toda_linha_escrita_pertence_ao_tenant(self):
        escrever(dados_de_exemplo(), self.coop)

        for modelo in (Cenario, Fabrica, Armazem, Rota,
                       PrevisaoFabrica, PrevisaoArmazem, SafraUnidade):
            linhas = list(modelo.all_cooperativas.all())
            self.assertTrue(linhas, f'{modelo.__name__} não escreveu nada')
            for linha in linhas:
                self.assertEqual(
                    linha.cooperativa_id, self.coop.id,
                    f'{modelo.__name__} {linha.id} caiu no tenant errado',
                )

    def test_ids_sao_remapeados_e_nao_reaproveitam_os_do_legado(self):
        escrever(dados_de_exemplo(), self.coop)

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        fabrica = Fabrica.all_cooperativas.get(cenario_id=oficial.id)
        self.assertNotEqual(fabrica.id, 101)
        self.assertEqual(fabrica.nome, 'FÁBRICA RIO VERDE')

    def test_rota_aponta_para_fabrica_e_armazem_do_mesmo_cenario(self):
        escrever(dados_de_exemplo(), self.coop)

        for rota in Rota.all_cooperativas.all():
            self.assertEqual(rota.armazem.cenario_id, rota.cenario_id)
            self.assertEqual(rota.fabrica.cenario_id, rota.cenario_id)

    def test_safra_de_armazem_remapeia_entidade_id_para_o_armazem_django(self):
        escrever(dados_de_exemplo(), self.coop)

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        armazem = Armazem.all_cooperativas.get(cenario_id=oficial.id)
        safra = SafraUnidade.all_cooperativas.get(entidade_tipo='Armazém')

        self.assertEqual(safra.entidade_id, armazem.id)
        self.assertNotEqual(safra.entidade_id, 201)

    def test_safra_de_fabrica_remapeia_entidade_id_para_a_fabrica_django(self):
        escrever(dados_de_exemplo(), self.coop)

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        fabrica = Fabrica.all_cooperativas.get(cenario_id=oficial.id)
        safra = SafraUnidade.all_cooperativas.get(entidade_tipo='Fábrica')

        self.assertEqual(safra.entidade_id, fabrica.id)
        self.assertNotEqual(safra.entidade_id, 101)

    def test_safra_com_entidade_id_orfa_e_pulada_sem_abortar_o_espelhamento(self):
        """`entidade_id` não é FK dos dois lados no legado -- pode apontar
        para um armazém/fábrica que não existe mais. `clone_scenario` (o
        precedente que este código espelha) pula a linha órfã em vez de
        abortar; `escrever` deve fazer o mesmo, e a contagem devolvida deve
        refletir apenas o que foi de fato gravado."""
        dados = dados_de_exemplo()
        dados.safras.append({
            'cenario_id': 6, 'entidade_tipo': 'Armazém', 'entidade_id': 999999,
            'data_inicio': datetime.date(2026, 2, 1), 'data_fim': datetime.date(2026, 5, 31),
        })

        contagens = escrever(dados, self.coop)

        self.assertEqual(contagens['safras'], 2)
        self.assertEqual(SafraUnidade.all_cooperativas.count(), 2)

    def test_previsao_segue_a_fabrica_do_cenario_correspondente(self):
        escrever(dados_de_exemplo(), self.coop)

        replanejado = Cenario.all_cooperativas.get(nome='Replanejado com Vendas')
        fabrica = Fabrica.all_cooperativas.get(cenario_id=replanejado.id)
        previsao = PrevisaoFabrica.all_cooperativas.get(fabrica_id=fabrica.id)

        self.assertEqual(previsao.vendas, 1800.0)

    def test_data_criacao_vira_aware_sem_warning_de_naive_datetime(self):
        """Com USE_TZ=True, o Django NÃO trata um DateTimeField naive como
        UTC: ele emite um RuntimeWarning e grava usando o fuso padrão
        (America/Sao_Paulo), o mesmo resultado que `_data_criacao_aware`
        produz explicitamente. O motivo de tornar o valor aware antes de
        gravar não é evitar um deslocamento de horário -- é evitar esse
        RuntimeWarning, já que 'saída de teste impecável' é uma restrição
        deste projeto (ver CLAUDE.md)."""
        with warnings.catch_warnings(record=True) as capturado:
            warnings.simplefilter('always')
            escrever(dados_de_exemplo(), self.coop)

        naive = [w for w in capturado if issubclass(w.category, RuntimeWarning)
                 and 'naive datetime' in str(w.message)]
        self.assertEqual(naive, [], f'escrita emitiu RuntimeWarning de naive datetime: {naive}')

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        local = timezone.localtime(oficial.data_criacao)

        self.assertIsNotNone(oficial.data_criacao.tzinfo)
        self.assertEqual(
            (local.year, local.month, local.day, local.hour, local.minute),
            (2026, 6, 1, 14, 19),
        )

    def test_data_criacao_none_usa_default_do_modelo(self):
        """`Cenario.data_criacao` é nullable no legado, mas NOT NULL no Django
        (`default=timezone.now`). Um `None` explícito bypassa esse default e
        vira `IntegrityError`; a escrita deve cair no default em vez disso."""
        dados = dados_de_exemplo()
        dados.cenarios[1]['data_criacao'] = None

        escrever(dados, self.coop)

        replanejado = Cenario.all_cooperativas.get(nome='Replanejado com Vendas')
        self.assertIsNotNone(replanejado.data_criacao)

    def test_previsao_com_recebimento_e_vendas_none_grava_como_zero(self):
        """`recebimento_produtor`/`vendas` são nullable no legado; os campos
        Django são `FloatField(default=0)`, NOT NULL. Um `None` explícito
        deve cair no default -- mesmo tratamento que `data_criacao` já
        recebe (ver `_zero_se_none`)."""
        dados = dados_de_exemplo()
        dados.previsoes_fabrica[0]['recebimento_produtor'] = None
        dados.previsoes_fabrica[0]['vendas'] = None
        dados.previsoes_armazem[0]['recebimento_produtor'] = None
        dados.previsoes_armazem[0]['vendas'] = None

        escrever(dados, self.coop)

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        fabrica = Fabrica.all_cooperativas.get(cenario_id=oficial.id)
        armazem = Armazem.all_cooperativas.get(cenario_id=oficial.id)
        previsao_fabrica = PrevisaoFabrica.all_cooperativas.get(fabrica_id=fabrica.id)
        previsao_armazem = PrevisaoArmazem.all_cooperativas.get(armazem_id=armazem.id)

        self.assertEqual(previsao_fabrica.recebimento_produtor, 0)
        self.assertEqual(previsao_fabrica.vendas, 0)
        self.assertEqual(previsao_armazem.recebimento_produtor, 0)
        self.assertEqual(previsao_armazem.vendas, 0)

    def test_cenario_editado_a_mao_no_django_e_perdido_ao_reespelhar(self):
        """Consequência aceita da estratégia apagar-e-recarregar (spec §3):
        uma linha que existe só do lado Django -- nunca veio do legado --
        desaparece sem aviso na execução seguinte."""
        Cenario.all_cooperativas.create(
            cooperativa=self.coop, nome='Editado à mão', is_oficial=False,
        )

        escrever(dados_de_exemplo(), self.coop)

        self.assertFalse(
            Cenario.all_cooperativas.filter(
                cooperativa=self.coop, nome='Editado à mão',
            ).exists()
        )

    def test_e_idempotente_entre_execucoes(self):
        primeira = escrever(dados_de_exemplo(), self.coop)
        segunda = escrever(dados_de_exemplo(), self.coop)

        self.assertEqual(primeira, segunda)
        self.assertEqual(Cenario.all_cooperativas.count(), 2)
        self.assertEqual(Fabrica.all_cooperativas.count(), 2)
        self.assertEqual(Rota.all_cooperativas.count(), 2)
        self.assertEqual(SafraUnidade.all_cooperativas.count(), 2)

    def test_nao_toca_nas_linhas_de_um_tenant_vizinho(self):
        vizinha = Cooperativa.objects.create(nome='Outra', slug='outra')
        cenario_vizinho = Cenario.all_cooperativas.create(
            cooperativa=vizinha, nome='Intocado', is_oficial=True,
        )
        Fabrica.all_cooperativas.create(
            cooperativa=vizinha, cenario=cenario_vizinho, nome='NÃO MEXER',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )

        escrever(dados_de_exemplo(), self.coop)
        escrever(dados_de_exemplo(), self.coop)

        self.assertEqual(Cenario.all_cooperativas.filter(cooperativa=vizinha).count(), 1)
        self.assertEqual(Fabrica.all_cooperativas.filter(cooperativa=vizinha).count(), 1)
        self.assertTrue(
            Fabrica.all_cooperativas.filter(cooperativa=vizinha, nome='NÃO MEXER').exists()
        )
