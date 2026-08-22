from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.core.middleware import CooperativaScopeMiddleware
from apps.core.models import Cooperativa, User
from apps.core.tenancy import obter_cooperativa_atual


class CooperativaScopeMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria_fabrica',
            cooperativa=self.cooperativa,
            papel=User.PAPEL_USUARIO_FABRICA,
        )

    def test_sets_cooperativa_from_authenticated_user_during_request(self):
        observado = {}

        def get_response(request):
            observado['cooperativa_id'] = obter_cooperativa_atual()
            return 'resposta'

        middleware = CooperativaScopeMiddleware(get_response)
        request = self.factory.get('/')
        request.user = self.user

        middleware(request)

        self.assertEqual(observado['cooperativa_id'], self.cooperativa.id)

    def test_resets_cooperativa_after_request(self):
        middleware = CooperativaScopeMiddleware(lambda request: 'resposta')
        request = self.factory.get('/')
        request.user = self.user

        middleware(request)

        self.assertIsNone(obter_cooperativa_atual())

    def test_anonymous_user_has_no_cooperativa(self):
        observado = {}

        def get_response(request):
            observado['cooperativa_id'] = obter_cooperativa_atual()
            return 'resposta'

        middleware = CooperativaScopeMiddleware(get_response)
        request = self.factory.get('/')
        request.user = AnonymousUser()

        middleware(request)

        self.assertIsNone(observado['cooperativa_id'])
