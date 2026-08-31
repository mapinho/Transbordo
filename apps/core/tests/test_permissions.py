from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.core import permissions as p
from apps.core.models import Cooperativa, User

PAPEIS = {
    'admin_vector': (False, User.PAPEL_ADMIN_VECTOR),
    'admin_cooperativa': (True, User.PAPEL_ADMIN_COOPERATIVA),
    'usuario_fabrica': (True, User.PAPEL_USUARIO_FABRICA),
    'usuario_armazem': (True, User.PAPEL_USUARIO_ARMAZEM),
}


class PermissionsMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        cls.users = {}
        for nome, (tem_coop, papel) in PAPEIS.items():
            cls.users[nome] = User.objects.create_user(
                username=nome, email=f'{nome}@t.test', papel=papel,
                cooperativa=cls.coop if tem_coop else None,
            )

    def test_predicados(self):
        casos = {
            'e_admin_vector': {'admin_vector'},
            'e_admin_cooperativa': {'admin_cooperativa'},
            'pode_gerir_usuarios': {'admin_vector', 'admin_cooperativa'},
            'pode_editar_fabricas': {'admin_cooperativa', 'usuario_fabrica'},
            'pode_editar_armazens': {'admin_cooperativa', 'usuario_armazem'},
        }
        for fn_nome, permitidos in casos.items():
            fn = getattr(p, fn_nome)
            for papel_nome, user in self.users.items():
                self.assertEqual(fn(user), papel_nome in permitidos, f'{fn_nome}/{papel_nome}')

    def test_papel_required_decorator(self):
        @p.papel_required(User.PAPEL_USUARIO_FABRICA)
        def view(request):
            return HttpResponse('ok')

        req = RequestFactory().get('/')
        req.user = self.users['usuario_fabrica']
        self.assertEqual(view(req).status_code, 200)
        req.user = self.users['usuario_armazem']
        with self.assertRaises(PermissionDenied):
            view(req)

    def test_requer_admin_vector_decorator(self):
        @p.requer_admin_vector
        def view(request):
            return HttpResponse('ok')

        req = RequestFactory().get('/')
        req.user = self.users['admin_vector']
        self.assertEqual(view(req).status_code, 200)
        req.user = self.users['admin_cooperativa']
        with self.assertRaises(PermissionDenied):
            view(req)


class SuperMembroAdminVectorTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.coop = Cooperativa.objects.create(nome="A", slug="a")
        self.vector = User.objects.create_user(
            username="v2", email="v2@t.test", papel=User.PAPEL_ADMIN_VECTOR,
        )

    def _req(self, session):
        r = self.rf.get("/")
        r.user = self.vector
        r.session = session
        return r

    def test_requer_membro_organizacao_com_org(self):
        @p.requer_membro_organizacao
        def view(request):
            return HttpResponse("ok")
        self.assertEqual(view(self._req({"org_corrente_id": self.coop.id})).status_code, 200)

    def test_requer_membro_organizacao_sem_org(self):
        @p.requer_membro_organizacao
        def view(request):
            return HttpResponse("ok")
        with self.assertRaises(PermissionDenied):
            view(self._req({}))

    def test_pode_editar_fabricas_admin_vector_com_org(self):
        self.assertTrue(p.pode_editar_fabricas(self.vector, self._req({"org_corrente_id": self.coop.id})))
        self.assertFalse(p.pode_editar_fabricas(self.vector, self._req({})))
