from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from apps.core.models import Cooperativa, User


class UserEmailTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')

    def test_email_obrigatorio(self):
        user = User(username='sem-email', papel=User.PAPEL_USUARIO_FABRICA, cooperativa=self.coop)
        with self.assertRaises(ValidationError):
            user.full_clean(exclude=['password'])

    def test_email_unico(self):
        User.objects.create_user(
            username='a', email='dup@coop.test',
            papel=User.PAPEL_USUARIO_FABRICA, cooperativa=self.coop,
        )
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                username='b', email='dup@coop.test',
                papel=User.PAPEL_USUARIO_ARMAZEM, cooperativa=self.coop,
            )
