from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from apps.core.adapters import AssociateByEmailSocialAdapter
from apps.core.models import Cooperativa, User


def _request():
    request = RequestFactory().get('/accounts/google/login/callback/')
    request.session = SessionStore()
    request._messages = FallbackStorage(request)
    return request


def _sociallogin(email):
    return SocialLogin(
        user=User(email=email),
        account=SocialAccount(provider='google', uid='uid-123'),
    )


class AssociateByEmailSocialAdapterTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='ana', email='ana@coop-a.test',
            papel=User.PAPEL_USUARIO_FABRICA, cooperativa=self.coop,
        )
        self.adapter = AssociateByEmailSocialAdapter()

    def test_email_conhecido_conecta_conta(self):
        sl = _sociallogin('ANA@coop-a.test')
        self.adapter.pre_social_login(_request(), sl)
        self.assertTrue(SocialAccount.objects.filter(user=self.user, provider='google').exists())

    def test_email_desconhecido_rejeita_sem_criar_usuario(self):
        antes = User.objects.count()
        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(_request(), _sociallogin('estranho@fora.test'))
        self.assertEqual(User.objects.count(), antes)

    def test_signup_social_fechado(self):
        self.assertFalse(self.adapter.is_open_for_signup(_request(), _sociallogin('x@y.test')))
