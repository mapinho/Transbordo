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
