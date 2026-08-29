import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = 'Cria o primeiro usuário Admin Vector (bootstrap único).'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('--email', required=True)
        parser.add_argument(
            '--password-from-env', action='store_true',
            help='Lê a senha de ADMIN_VECTOR_PASSWORD em vez de perguntar interativamente.',
        )

    def handle(self, *args, **options):
        if User.objects.filter(papel=User.PAPEL_ADMIN_VECTOR).exists():
            raise CommandError(
                'Já existe um Admin Vector. Crie os demais pela tela de gestão de usuários.'
            )

        if options['password_from_env']:
            password = os.environ.get('ADMIN_VECTOR_PASSWORD')
            if not password:
                raise CommandError('ADMIN_VECTOR_PASSWORD não definida no ambiente.')
        else:
            password = getpass.getpass('Senha: ')
            if password != getpass.getpass('Senha (novamente): '):
                raise CommandError('As senhas não conferem.')

        user = User(
            username=options['username'], email=options['email'],
            papel=User.PAPEL_ADMIN_VECTOR, cooperativa=None,
            is_staff=True, is_superuser=True,
        )
        try:
            validate_password(password, user)
            user.set_password(password)
            user.full_clean(exclude=['password'])
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        user.save()
        self.stdout.write(self.style.SUCCESS(f'Admin Vector "{user.username}" criado.'))
