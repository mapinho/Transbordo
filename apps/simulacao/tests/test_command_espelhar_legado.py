import datetime
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.core.models import Cooperativa, User
from apps.simulacao.legado import DadosLegado
from apps.simulacao.models import Cenario, Fabrica

CAMINHO = 'apps.simulacao.management.commands.espelhar_legado'


def dados_minimos():
    return DadosLegado(
        cenarios=[{'id': 6, 'nome': 'Oficial (Planejado)', 'is_oficial': True,
                   'data_criacao': datetime.datetime(2026, 6, 1, 14, 19, 30)}],
        fabricas=[{'id': 101, 'cenario_id': 6, 'nome': 'FÁBRICA RIO VERDE',
                   'capacidade_estatica': 50000, 'capacidade_esmagamento_diaria': 1200,
                   'capacidade_recebimento_diaria': 2000, 'limite_caminhoes': 60,
                   'carga_media_caminhao': 36, 'estoque_inicial': 8000}],
    )


@override_settings(DEBUG=True)
class EspelharLegadoTests(TestCase):
    def setUp(self):
        patch_sessao = mock.patch(f'{CAMINHO}.abrir_sessao_legado')
        patch_leitura = mock.patch(f'{CAMINHO}.ler_legado', return_value=dados_minimos())
        patch_env = mock.patch.dict(
            'os.environ', {'DATABASE_URL': 'postgresql://x/y'}, clear=False,
        )
        patch_sessao.start()
        patch_leitura.start()
        patch_env.start()
        self.addCleanup(patch_sessao.stop)
        self.addCleanup(patch_leitura.stop)
        self.addCleanup(patch_env.stop)

    def test_cria_o_tenant_quando_ele_nao_existe(self):
        call_command('espelhar_legado', '--yes', stdout=StringIO())

        coop = Cooperativa.objects.get(slug='comigo')
        self.assertEqual(Cenario.all_cooperativas.filter(cooperativa=coop).count(), 1)
        self.assertEqual(Fabrica.all_cooperativas.filter(cooperativa=coop).count(), 1)

    def test_reusa_o_tenant_quando_ele_ja_existe(self):
        existente = Cooperativa.objects.create(nome='Comigo', slug='comigo')

        call_command('espelhar_legado', '--yes', stdout=StringIO())

        self.assertEqual(Cooperativa.objects.filter(slug='comigo').count(), 1)
        self.assertEqual(
            Cenario.all_cooperativas.filter(cooperativa=existente).count(), 1
        )

    def test_respeita_o_slug_informado(self):
        call_command('espelhar_legado', '--cooperativa-slug', 'outra', '--yes',
                     stdout=StringIO())

        self.assertTrue(Cooperativa.objects.filter(slug='outra').exists())
        self.assertFalse(Cooperativa.objects.filter(slug='comigo').exists())

    def test_imprime_as_contagens_escritas(self):
        saida = StringIO()

        call_command('espelhar_legado', '--yes', stdout=saida)

        texto = saida.getvalue()
        self.assertIn('cenarios', texto)
        self.assertIn('fabricas', texto)

    def test_repoint_de_usuario_existente(self):
        User.objects.create_user(
            username='teste', password='x', papel=User.PAPEL_ADMIN_COOPERATIVA,
            cooperativa=Cooperativa.objects.create(nome='Antiga', slug='antiga'),
        )

        call_command('espelhar_legado', '--usuario', 'teste', '--yes', stdout=StringIO())

        usuario = User.objects.get(username='teste')
        self.assertEqual(usuario.cooperativa.slug, 'comigo')

    def test_falha_alto_quando_o_usuario_informado_nao_existe(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('espelhar_legado', '--usuario', 'inexistente', '--yes',
                         stdout=StringIO())

        self.assertIn('inexistente', str(ctx.exception))

    def test_usuario_inexistente_nao_deixa_tenant_orfao(self):
        """A validação do usuário precisa vir antes do get_or_create do tenant."""
        with self.assertRaises(CommandError):
            call_command('espelhar_legado', '--usuario', 'inexistente', '--yes',
                         stdout=StringIO())

        self.assertFalse(Cooperativa.objects.filter(slug='comigo').exists())

    def test_sem_yes_e_sem_confirmacao_nao_escreve_nada(self):
        with mock.patch(f'{CAMINHO}.input', return_value='n', create=True):
            call_command('espelhar_legado', stdout=StringIO())

        self.assertEqual(Cenario.all_cooperativas.count(), 0)
        self.assertFalse(Cooperativa.objects.filter(slug='comigo').exists())

    def test_sem_yes_mas_com_confirmacao_escreve(self):
        with mock.patch(f'{CAMINHO}.input', return_value='s', create=True):
            call_command('espelhar_legado', stdout=StringIO())

        self.assertEqual(Cenario.all_cooperativas.count(), 1)


@override_settings(DEBUG=False)
class GuardaDeProducaoTests(TestCase):
    def test_recusa_rodar_com_debug_desligado(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('espelhar_legado', '--yes', stdout=StringIO())

        self.assertIn('DEBUG', str(ctx.exception))
        self.assertEqual(Cooperativa.objects.count(), 0)
