from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class NoSignupAccountAdapter(DefaultAccountAdapter):
    """Cadastro local sempre fechado — o Admin Vector cria as contas."""

    def is_open_for_signup(self, request):
        return False


class AssociateByEmailSocialAdapter(DefaultSocialAccountAdapter):
    """Login social nunca cria usuário; associa a um `User` pré-cadastrado
    por e-mail (corpo real de `pre_social_login` na Task 3)."""

    def is_open_for_signup(self, request, sociallogin):
        return False
