from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings

from apps.core.models import Cooperativa, User
from apps.integracoes.models import ApiKey
from apps.simulacao.models import Cenario, ConversaIA


def _count(tabela):
    with connection.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM {tabela}')
        return cur.fetchone()[0]


class SanitizarPosRestoreTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop Real', slug='coop-real')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.coop, nome='Cenário Real')
        self.user = User.objects.create_user(
            username='dev', email='dev@x.test', password='x',
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop,
        )
        ApiKey.objects.create(cooperativa=self.coop, nome='dev key')
        ConversaIA.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, usuario=self.user,
        )
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO procrastinate_jobs (queue_name, task_name) "
                "VALUES ('default', 'dummy')"
            )
            cur.execute(
                "INSERT INTO django_session (session_key, session_data, expire_date) "
                "VALUES ('k', 'd', now())"
            )

    def test_apaga_identidade_e_estado_preserva_dominio(self):
        call_command('sanitizar_pos_restore')
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(ApiKey.objects.count(), 0)
        self.assertEqual(ConversaIA.all_cooperativas.count(), 0)
        self.assertEqual(_count('procrastinate_jobs'), 0)
        self.assertEqual(_count('django_session'), 0)
        self.assertEqual(Cooperativa.objects.count(), 1)
        self.assertEqual(Cenario.all_cooperativas.count(), 1)

    @override_settings(ALLOWED_HOSTS=['transbordo.example.com', 'localhost'])
    def test_ajusta_django_site(self):
        call_command('sanitizar_pos_restore')
        site = Site.objects.get(pk=settings.SITE_ID)
        self.assertEqual(site.domain, 'transbordo.example.com')
        self.assertEqual(site.name, 'transbordo.example.com')

    def test_idempotente(self):
        call_command('sanitizar_pos_restore')
        call_command('sanitizar_pos_restore')
        self.assertEqual(User.objects.count(), 0)

    def test_dry_run_nao_escreve(self):
        call_command('sanitizar_pos_restore', '--dry-run')
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(ApiKey.objects.count(), 1)
        self.assertEqual(_count('procrastinate_jobs'), 1)
