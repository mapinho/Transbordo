from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa, User


class UsuariosCrudTests(TestCase):
    def setUp(self):
        self.coop_a = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        self.vector = User.objects.create_user(
            username='vector', email='vector@t.test', password='x', papel=User.PAPEL_ADMIN_VECTOR,
        )
        self.admin_a = User.objects.create_user(
            username='adA', email='ada@t.test', password='x',
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop_a,
        )
        self.user_b = User.objects.create_user(
            username='ub', email='ub@t.test', password='x',
            papel=User.PAPEL_USUARIO_FABRICA, cooperativa=self.coop_b,
        )

    def test_admin_vector_ve_todos(self):
        self.client.force_login(self.vector)
        response = self.client.get(reverse('gestao:usuarios'))
        self.assertContains(response, 'adA')
        self.assertContains(response, 'ub')

    def test_admin_cooperativa_ve_so_os_seus(self):
        self.client.force_login(self.admin_a)
        response = self.client.get(reverse('gestao:usuarios'))
        self.assertNotContains(response, 'ub@t.test')
        self.assertNotContains(
            response, reverse('gestao:usuario_editar', args=[self.user_b.id])
        )

    def test_usuario_fabrica_recebe_403(self):
        self.client.force_login(self.user_b)
        self.assertEqual(self.client.get(reverse('gestao:usuarios')).status_code, 403)

    def test_usuario_fabrica_nao_ve_link_usuarios_no_menu(self):
        self.client.force_login(self.user_b)
        from apps.simulacao.models import Cenario
        Cenario.all_cooperativas.create(cooperativa=self.coop_b, nome='C')
        html = self.client.get(reverse('simulacao:cenarios_list')).content.decode()
        self.assertNotIn(reverse('gestao:usuarios'), html)

    def test_admin_cooperativa_cria_usuario_na_propria_coop(self):
        self.client.force_login(self.admin_a)
        response = self.client.post(reverse('gestao:usuario_novo'), {
            'username': 'novo', 'email': 'novo@coop-a.test', 'first_name': '',
            'papel': User.PAPEL_USUARIO_ARMAZEM, 'is_active': 'on', 'senha': 'senha-forte-999',
        })
        self.assertEqual(response.status_code, 302)
        novo = User.objects.get(username='novo')
        self.assertEqual(novo.cooperativa, self.coop_a)
        self.assertEqual(novo.papel, User.PAPEL_USUARIO_ARMAZEM)

    def test_admin_cooperativa_nao_cria_admin_vector(self):
        self.client.force_login(self.admin_a)
        response = self.client.post(reverse('gestao:usuario_novo'), {
            'username': 'hack', 'email': 'hack@t.test',
            'papel': User.PAPEL_ADMIN_VECTOR, 'is_active': 'on', 'senha': 'senha-forte-999',
        })
        self.assertEqual(response.status_code, 200)  # form inválido, re-render
        self.assertFalse(User.objects.filter(username='hack').exists())

    def test_admin_cooperativa_nao_edita_usuario_de_outra_coop(self):
        self.client.force_login(self.admin_a)
        self.assertEqual(
            self.client.get(reverse('gestao:usuario_editar', args=[self.user_b.id])).status_code,
            404,
        )
