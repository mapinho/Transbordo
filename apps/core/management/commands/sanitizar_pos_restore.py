from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand
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
)


class Command(BaseCommand):
    help = (
        'Higieniza o banco logo apos restaurar um dump de desenvolvimento em '
        'producao: apaga usuarios/ApiKeys/conversas de dev, zera filas do '
        'procrastinate e sessoes, e ajusta o django_site a partir de '
        'ALLOWED_HOSTS. Idempotente. Nao toca a Cooperativa nem o dominio de '
        'simulacao.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='So imprime o que seria apagado, sem escrever.',
        )

    def _contar(self, tabela):
        with connection.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM {tabela}')
            return cur.fetchone()[0]

    def handle(self, *args, **options):
        contagens = {
            'ApiKey': ApiKey.objects.count(),
            'User': User.objects.count(),
            'ConversaIA': ConversaIA.all_cooperativas.count(),
        }
        for t in TABELAS_ESTADO:
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

        with transaction.atomic():
            ApiKey.objects.all().delete()
            User.objects.all().delete()
            ConversaIA.all_cooperativas.all().delete()
            with connection.cursor() as cur:
                cur.execute(
                    'TRUNCATE TABLE '
                    + ', '.join(TABELAS_ESTADO)
                    + ' RESTART IDENTITY'
                )
            if host:
                Site.objects.filter(pk=settings.SITE_ID).update(domain=host, name=host)

        self.stdout.write(self.style.SUCCESS('Higienizacao concluida.'))
