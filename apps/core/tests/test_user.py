from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.models import Cooperativa, User


class UserTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')

    def test_admin_vector_sem_cooperativa_e_valido(self):
        user = User(
            username='admin_vector', email='admin_vector@vector.test',
            papel=User.PAPEL_ADMIN_VECTOR, cooperativa=None,
        )

        user.full_clean(exclude=['password'])

    def test_admin_vector_com_cooperativa_e_invalido(self):
        user = User(
            username='admin_vector', email='admin_vector@vector.test',
            papel=User.PAPEL_ADMIN_VECTOR, cooperativa=self.cooperativa,
        )

        with self.assertRaises(ValidationError):
            user.full_clean(exclude=['password'])

    def test_usuario_fabrica_sem_cooperativa_e_invalido(self):
        user = User(
            username='usuario_fabrica', email='usuario_fabrica@coop-a.test',
            papel=User.PAPEL_USUARIO_FABRICA, cooperativa=None,
        )

        with self.assertRaises(ValidationError):
            user.full_clean(exclude=['password'])

    def test_usuario_fabrica_com_cooperativa_e_valido(self):
        user = User(
            username='usuario_fabrica', email='usuario_fabrica@coop-a.test',
            papel=User.PAPEL_USUARIO_FABRICA, cooperativa=self.cooperativa,
        )

        user.full_clean(exclude=['password'])
