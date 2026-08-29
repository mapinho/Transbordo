from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect


class NoSignupAccountAdapter(DefaultAccountAdapter):
    """Cadastro local sempre fechado — o Admin Vector cria as contas."""

    def is_open_for_signup(self, request):
        return False


class AssociateByEmailSocialAdapter(DefaultSocialAccountAdapter):
    """Login social nunca cria usuário; associa a um `User` pré-cadastrado
    por e-mail (case-insensitive). Sem correspondência, volta ao login com
    mensagem em pt-BR."""

    def is_open_for_signup(self, request, sociallogin):
        return False

    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return
        email = (sociallogin.user.email or '').strip()
        user = get_user_model().objects.filter(email__iexact=email).first() if email else None
        if user is None:
            messages.error(
                request,
                'Nenhuma conta cadastrada para este e-mail. Contate o administrador.',
            )
            raise ImmediateHttpResponse(redirect('account_login'))
        sociallogin.connect(request, user)
