import sys

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.core.models import User
from apps.integracoes.models import ApiKey
from apps.simulacao.models import ConversaIA

TABELAS_ESTADO = (
    'procrastinate_jobs',
    'procrastinate_events',
    'procrastinate_periodic_defers',
    'procrastinate_workers',
    'django_session',
    'socialaccount_socialapp',
)

CONFIRMACAO = (
    'Isto apaga usuarios/ApiKeys/conversas e zera filas/sessoes. '
    'Digite "sim" para continuar: '
)


class Command(BaseCommand):
    help = (
        'Higieniza o banco logo apos restaurar um dump de desenvolvimento em '
        'producao: apaga usuarios/ApiKeys/conversas de dev, zera filas do '
        'procrastinate, sessoes e SocialApps de dev, e ajusta o django_site a '
        'partir de ALLOWED_HOSTS. Idempotente. Nao toca a Cooperativa nem o '
        'dominio de simulacao.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='So imprime o que seria apagado, sem escrever.',
        )
        parser.add_argument(
            '--noinput', '--no-input', action='store_true', dest='noinput',
            help='Nao pede confirmacao interativa.',
        )

    def _contar(self, tabela):
        with connection.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM {tabela}')
            return cur.fetchone()[0]

    def _tabelas_existentes(self):
        with connection.cursor() as cur:
            cur.execute(
                "SELECT t FROM unnest(%s::text[]) AS t "
                "WHERE to_regclass(t) IS NOT NULL",
                [list(TABELAS_ESTADO)],
            )
            return [r[0] for r in cur.fetchall()]

    def handle(self, *args, **options):
        existentes = self._tabelas_existentes()

        contagens = {
            'ApiKey': ApiKey.objects.count(),
            'User': User.objects.count(),
            'ConversaIA': ConversaIA.all_cooperativas.count(),
        }
        for t in existentes:
            contagens[t] = self._contar(t)
        for nome, n in contagens.items():
            self.stdout.write(f'  {nome}: {n}')

        host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else ''
        if host in ('', '*'):
            self.stdout.write(self.style.WARNING(
                'ALLOWED_HOSTS[0] inutilizavel; django_site nao sera ajustado.'
            ))
            host = None

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('--dry-run: nada foi escrito.'))
            return

        if not options['noinput'] and sys.stdin.isatty():
            if input(CONFIRMACAO).strip() != 'sim':
                raise CommandError('Abortado: confirmacao nao recebida.')

        with transaction.atomic():
            ApiKey.objects.all().delete()
            User.objects.all().delete()
            ConversaIA.all_cooperativas.all().delete()
            if existentes:
                with connection.cursor() as cur:
                    # Descarrega triggers de constraint pendentes (inserts m2m na
                    # mesma transacao) — senao o Postgres recusa TRUNCATE.
                    cur.execute('SET CONSTRAINTS ALL IMMEDIATE')
                    cur.execute(
                        'TRUNCATE TABLE '
                        + ', '.join(existentes)
                        + ' RESTART IDENTITY CASCADE'
                    )
            if host:
                atualizadas = Site.objects.filter(pk=settings.SITE_ID).update(
                    domain=host, name=host,
                )
                if not atualizadas:
                    self.stdout.write(self.style.WARNING(
                        'django_site pk=%s ausente — dominio nao ajustado.'
                        % settings.SITE_ID
                    ))

        self.stdout.write(self.style.SUCCESS('Higienizacao concluida.'))
