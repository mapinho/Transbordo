from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class Cooperativa(models.Model):
    """Raiz do tenant: cada cooperativa é isolada das demais (ver apps.core.tenancy)."""

    nome = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    ativo = models.BooleanField(default=True)
    dias_janela_safra_padrao = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            'Parâmetro placeholder para a janela de safra padrão da cooperativa; '
            'semântica real definida quando SafraUnidade for portado (próxima fase).'
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cooperativa'
        verbose_name_plural = 'Cooperativas'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class User(AbstractUser):
    """Identidade de login. `cooperativa=None` só é válido para o papel Admin Vector
    (cross-tenant); os demais papéis pertencem a exatamente uma cooperativa.

    Não herda `CooperativaScopedModel` de propósito: `cooperativa` aqui é nullable
    (Admin Vector) e a autenticação precisa funcionar antes que qualquer escopo de
    tenant esteja definido no contexto — teria uma dependência circular."""

    PAPEL_ADMIN_VECTOR = 'admin_vector'
    PAPEL_ADMIN_COOPERATIVA = 'admin_cooperativa'
    PAPEL_USUARIO_FABRICA = 'usuario_fabrica'
    PAPEL_USUARIO_ARMAZEM = 'usuario_armazem'
    PAPEL_CHOICES = [
        (PAPEL_ADMIN_VECTOR, 'Admin Vector'),
        (PAPEL_ADMIN_COOPERATIVA, 'Admin Cooperativa'),
        (PAPEL_USUARIO_FABRICA, 'Usuário Fábrica'),
        (PAPEL_USUARIO_ARMAZEM, 'Usuário Armazém'),
    ]

    email = models.EmailField('endereço de e-mail', unique=True)
    cooperativa = models.ForeignKey(
        'core.Cooperativa', on_delete=models.PROTECT, null=True, blank=True, related_name='usuarios'
    )
    papel = models.CharField(max_length=20, choices=PAPEL_CHOICES)

    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(papel='admin_vector', cooperativa__isnull=True)
                    | (~models.Q(papel='admin_vector') & models.Q(cooperativa__isnull=False))
                ),
                name='user_papel_cooperativa_coerentes',
            ),
        ]

    def clean(self):
        super().clean()
        if self.papel == self.PAPEL_ADMIN_VECTOR and self.cooperativa_id is not None:
            raise ValidationError('Admin Vector não pertence a nenhuma cooperativa.')
        if self.papel != self.PAPEL_ADMIN_VECTOR and self.cooperativa_id is None:
            raise ValidationError('Este papel exige uma cooperativa.')
