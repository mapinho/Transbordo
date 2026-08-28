import secrets

from django.db import models


def gerar_chave() -> str:
    """Chave de API opaca. Referenciada por nome nas migrations, então
    precisa ser uma função de módulo (não um lambda)."""
    return secrets.token_urlsafe(32)


class ApiKey(models.Model):
    """Credencial de API processo-a-processo, uma ou mais por cooperativa.

    Não herda `CooperativaScopedModel`: é justamente o que *define* a
    cooperativa corrente de um request via header `X-API-Key`, e a busca
    da chave acontece antes de qualquer escopo de tenant existir. Ver
    `docs/decisions/0008-...` e a spec da Fase 6.
    """

    cooperativa = models.ForeignKey(
        'core.Cooperativa', on_delete=models.PROTECT, related_name='api_keys'
    )
    nome = models.CharField(max_length=120, help_text='Rótulo do serviço que usa esta chave.')
    chave = models.CharField(max_length=64, unique=True, editable=False, default=gerar_chave)
    ativo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Chave de API'
        verbose_name_plural = 'Chaves de API'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.nome} ({self.cooperativa})'
