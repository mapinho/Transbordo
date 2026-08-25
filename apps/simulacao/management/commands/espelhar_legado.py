"""Espelha os dados de entrada do banco legado para um tenant Django.

Ferramenta de DESENVOLVIMENTO e DESTRUTIVA: apaga tudo o que o tenant alvo
tem antes de recarregar. Ver
docs/superpowers/specs/2026-08-24-espelhamento-dados-legado-design.md.
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Cooperativa, User
from apps.simulacao.legado import abrir_sessao_legado, escrever, ler_legado
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, PrevisaoArmazem, PrevisaoFabrica, Rota, SafraUnidade,
)

MODELOS_AFETADOS = (
    Cenario, Fabrica, Armazem, Rota, PrevisaoFabrica, PrevisaoArmazem, SafraUnidade,
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

        # Validar o usuário ANTES de criar o tenant: um username errado não pode
        # deixar uma Cooperativa órfã para trás.
        usuario = None
        if options['usuario']:
            try:
                usuario = User.objects.get(username=options['usuario'])
            except User.DoesNotExist:
                raise CommandError(
                    f"Usuário '{options['usuario']}' não existe. Este comando repointa "
                    'um usuário existente, não cria usuários.'
                )

        slug = options['cooperativa_slug']
        cooperativa, criada = Cooperativa.objects.get_or_create(
            slug=slug, defaults={'nome': slug.capitalize()},
        )

        if not options['yes'] and not self._confirmar(cooperativa, criada):
            self.stdout.write('Cancelado. Nada foi alterado.')
            return

        sessao = abrir_sessao_legado(database_url)
        try:
            dados = ler_legado(sessao)
        finally:
            sessao.close()

        contagens = escrever(dados, cooperativa)

        if usuario is not None:
            usuario.cooperativa = cooperativa
            usuario.save(update_fields=['cooperativa'])
            self.stdout.write(
                f"Usuário '{usuario.username}' repontado para '{cooperativa.nome}'."
            )

        self.stdout.write(self.style.SUCCESS(f'Espelhado para {cooperativa.nome}:'))
        for tabela, quantidade in contagens.items():
            self.stdout.write(f'  {tabela}: {quantidade}')

    def _confirmar(self, cooperativa, criada):
        if criada:
            self.stdout.write(
                f"Tenant '{cooperativa.slug}' será criado — nada a apagar."
            )
        else:
            self.stdout.write(
                f"ATENÇÃO: tudo o que o tenant '{cooperativa.slug}' tem hoje será "
                'APAGADO e recarregado do legado:'
            )
            for modelo in MODELOS_AFETADOS:
                total = modelo.all_cooperativas.filter(cooperativa=cooperativa).count()
                self.stdout.write(f'  {modelo.__name__}: {total} linha(s)')
        return input('Continuar? [s/N] ').strip().lower() == 's'
