import os

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.core.models import User


class CriarAdminVectorTests(TestCase):
    def setUp(self):
        self._senha = 'senha-vector-forte-123'
        os.environ['ADMIN_VECTOR_PASSWORD'] = self._senha

    def tearDown(self):
        os.environ.pop('ADMIN_VECTOR_PASSWORD', None)

    def test_usuario_criado_e_admin_vector(self):
        call_command('criar_admin_vector', 'vector', '--email', 'vector@transbordo.test',
                     '--password-from-env')
        u = User.objects.get(username='vector')
        self.assertEqual(u.papel, User.PAPEL_ADMIN_VECTOR)
        self.assertIsNone(u.cooperativa_id)
        self.assertTrue(u.is_staff and u.is_superuser)
        self.assertTrue(u.check_password(self._senha))

    def test_recusa_segundo_admin_vector(self):
        call_command('criar_admin_vector', 'vector', '--email', 'v1@transbordo.test',
                     '--password-from-env')
        with self.assertRaises(CommandError):
            call_command('criar_admin_vector', 'vector2', '--email', 'v2@transbordo.test',
                         '--password-from-env')

    def test_sem_senha_no_env_falha(self):
        os.environ.pop('ADMIN_VECTOR_PASSWORD', None)
        with self.assertRaises(CommandError):
            call_command('criar_admin_vector', 'vector', '--email', 'v@transbordo.test',
                         '--password-from-env')
