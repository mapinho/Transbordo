"""Espelha os dados de entrada do banco legado para um tenant Django.

Ferramenta de DESENVOLVIMENTO e DESTRUTIVA: apaga tudo o que o tenant alvo
tem antes de recarregar. Ver
docs/superpowers/specs/2026-08-24-espelhamento-dados-legado-design.md.
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from sqlalchemy.engine import make_url

from apps.core.models import Cooperativa, User
from apps.simulacao.legado import (
    MODELOS_APAGADOS, abrir_sessao_legado, escrever, ler_legado,
)


class Command(BaseCommand):
    help = 'Espelha os dados de entrada do banco legado para um tenant Django.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cooperativa-slug', default='comigo',
            help='Slug do tenant alvo; criado se não existir. Padrão: comigo.',
        )
        parser.add_argument(
            '--usuario', default=None,
            help='Username de um usuário JÁ EXISTENTE, a ser repontado para o tenant.',
        )
        parser.add_argument(
            '--yes', action='store_true',
            help='Pula a confirmação interativa.',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                'espelhar_legado é uma ferramenta de desenvolvimento e apaga o tenant '
                'inteiro antes de recarregar. Recusando rodar com DEBUG desligado.'
            )

        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise CommandError(
                'DATABASE_URL não definida. É a conexão do banco legado (stack '
                'Streamlit); ver .env.'
            )

        # Validar o usuário ANTES de criar o tenant ou ler o legado: nem um
        # username errado nem um papel incompatível com o repoint podem
        # deixar uma Cooperativa órfã ou uma leitura desperdiçada para trás.
        usuario = None
        if options['usuario']:
            try:
                usuario = User.objects.get(username=options['usuario'])
            except User.DoesNotExist:
                raise CommandError(
                    f"Usuário '{options['usuario']}' não existe. Este comando repointa "
                    'um usuário existente, não cria usuários.'
                ) from None
            if usuario.papel == User.PAPEL_ADMIN_VECTOR:
                raise CommandError(
                    f"Usuário '{usuario.username}' é Admin Vector: cross-tenant por "
                    'definição, não pode ser repontado para uma única cooperativa.'
                )

        self._imprimir_bancos_alvo(database_url)

        slug = options['cooperativa_slug']
        ja_existe = Cooperativa.objects.filter(slug=slug).exists()

        if not options['yes'] and not self._confirmar(slug, ja_existe):
            self.stdout.write('Cancelado. Nada foi alterado.')
            return

        sessao = abrir_sessao_legado(database_url)
        try:
            dados = ler_legado(sessao)
        finally:
            sessao.close()

        # get_or_create do tenant, escrever e o repoint do usuário formam uma
        # única unidade atômica: se qualquer um falhar, não sobra tenant nem
        # estado parcial. O `atomic()` interno de `escrever` aninha como
        # savepoint.
        with transaction.atomic():
            cooperativa, _ = Cooperativa.objects.get_or_create(
                slug=slug, defaults={'nome': slug.capitalize()},
            )

            contagens = escrever(dados, cooperativa)

            if usuario is not None:
                usuario.cooperativa = cooperativa
                usuario.save(update_fields=['cooperativa'])

        if usuario is not None:
            self.stdout.write(
                f"Usuário '{usuario.username}' repontado para '{cooperativa.nome}'."
            )

        self.stdout.write(self.style.SUCCESS(f'Espelhado para {cooperativa.nome}:'))
        for tabela, quantidade in contagens.items():
            self.stdout.write(f'  {tabela}: {quantidade}')

    def _imprimir_bancos_alvo(self, database_url):
        """Nunca imprime a senha do legado -- só host/database, via
        `make_url(...).render_as_string(hide_password=True)`."""
        legado_url = make_url(database_url).render_as_string(hide_password=True)
        django_db = settings.DATABASES['default']
        self.stdout.write(f'Legado (origem): {legado_url}')
        self.stdout.write(
            f"Django (destino): {django_db['NAME']}@{django_db['HOST']}"
        )

    def _confirmar(self, slug, ja_existe):
        if not ja_existe:
            self.stdout.write(
                f"Tenant '{slug}' será criado — nada a apagar."
            )
        else:
            self.stdout.write(
                f"ATENÇÃO: tudo o que o tenant '{slug}' tem hoje será "
                'APAGADO e recarregado do legado:'
            )
            for modelo in MODELOS_APAGADOS:
                total = modelo.all_cooperativas.filter(cooperativa__slug=slug).count()
                self.stdout.write(f'  {modelo.__name__}: {total} linha(s)')
        return input('Continuar? [s/N] ').strip().lower() == 's'
