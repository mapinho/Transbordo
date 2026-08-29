from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.tenancy import CooperativaScopedModel


class CenarioScopedModel(CooperativaScopedModel):
    """Base abstrata para models que pertencem a um Cenario (a maioria do
    domínio de simulação). `cenario` é obrigatório (ao contrário de
    `LogExecucao`, que declara seu próprio FK nullable -- ver ADR 0005).

    `clean()` prova que `cooperativa` e `cenario.cooperativa` nunca divergem
    -- sem essa checagem, nada impede que alguém crie uma Fabrica apontando
    para um Cenario de outra cooperativa (o `TenantManager` só filtra
    leituras; ver ADR 0001 e ADR 0006).
    """

    cenario = models.ForeignKey('simulacao.Cenario', on_delete=models.CASCADE)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.cenario_id is not None and self.cenario.cooperativa_id != self.cooperativa_id:
            raise ValidationError(
                'cooperativa não corresponde à cooperativa do cenario.'
            )


class Cenario(CooperativaScopedModel):
    nome = models.CharField(max_length=100)
    data_criacao = models.DateTimeField(default=timezone.now)
    is_oficial = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Cenário'
        verbose_name_plural = 'Cenários'
        ordering = ['nome']
        constraints = [
            models.UniqueConstraint(
                fields=['cooperativa', 'nome'],
                name='simulacao_cenario_unique_cooperativa_nome',
            ),
        ]

    def __str__(self):
        return self.nome


class Fabrica(CenarioScopedModel):
    nome = models.CharField(max_length=100)
    capacidade_estatica = models.FloatField()
    capacidade_esmagamento_diaria = models.FloatField()
    capacidade_recebimento_diaria = models.FloatField()
    limite_caminhoes = models.IntegerField()
    carga_media_caminhao = models.FloatField()
    estoque_inicial = models.FloatField()

    class Meta:
        verbose_name = 'Fábrica'
        verbose_name_plural = 'Fábricas'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Armazem(CenarioScopedModel):
    nome = models.CharField(max_length=100)
    capacidade_estatica = models.FloatField()
    capacidade_expedicao_diaria = models.FloatField()
    estoque_inicial = models.FloatField()

    class Meta:
        verbose_name = 'Armazém'
        verbose_name_plural = 'Armazéns'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Rota(CenarioScopedModel):
    armazem = models.ForeignKey(Armazem, on_delete=models.CASCADE, related_name='rotas')
    fabrica = models.ForeignKey(Fabrica, on_delete=models.CASCADE, related_name='rotas')
    distancia_km = models.FloatField()
    custo_frete_ton = models.FloatField()
    custo_frete_entressafra = models.FloatField(default=0)

    class Meta:
        verbose_name = 'Rota'
        verbose_name_plural = 'Rotas'

    def __str__(self):
        return f'{self.armazem} → {self.fabrica}'


class PrevisaoFabrica(CooperativaScopedModel):
    fabrica = models.ForeignKey(Fabrica, on_delete=models.CASCADE, related_name='previsoes')
    mes_referencia = models.DateField()
    recebimento_produtor = models.FloatField(default=0)
    vendas = models.FloatField(default=0)

    class Meta:
        verbose_name = 'Previsão de Fábrica'
        verbose_name_plural = 'Previsões de Fábrica'

    def __str__(self):
        return f'{self.fabrica} — {self.mes_referencia:%Y-%m}'

    def clean(self):
        super().clean()
        if self.fabrica_id is not None and self.fabrica.cooperativa_id != self.cooperativa_id:
            raise ValidationError('cooperativa não corresponde à cooperativa da fabrica.')


class PrevisaoArmazem(CooperativaScopedModel):
    armazem = models.ForeignKey(Armazem, on_delete=models.CASCADE, related_name='previsoes')
    mes_referencia = models.DateField()
    recebimento_produtor = models.FloatField(default=0)
    vendas = models.FloatField(default=0)

    class Meta:
        verbose_name = 'Previsão de Armazém'
        verbose_name_plural = 'Previsões de Armazém'

    def __str__(self):
        return f'{self.armazem} — {self.mes_referencia:%Y-%m}'

    def clean(self):
        super().clean()
        if self.armazem_id is not None and self.armazem.cooperativa_id != self.cooperativa_id:
            raise ValidationError('cooperativa não corresponde à cooperativa do armazem.')


class SafraUnidade(CenarioScopedModel):
    entidade_tipo = models.CharField(max_length=20)
    entidade_id = models.IntegerField()
    data_inicio = models.DateField()
    data_fim = models.DateField()

    class Meta:
        verbose_name = 'Safra da Unidade'
        verbose_name_plural = 'Safras das Unidades'

    def __str__(self):
        return f'{self.entidade_tipo} {self.entidade_id} ({self.data_inicio} a {self.data_fim})'


class MovimentacaoDiaria(CenarioScopedModel):
    data = models.DateField()
    armazem = models.ForeignKey(Armazem, on_delete=models.CASCADE)
    fabrica = models.ForeignKey(Fabrica, on_delete=models.CASCADE)
    quantidade_ton = models.FloatField()
    custo_total = models.FloatField()

    class Meta:
        verbose_name = 'Movimentação Diária'
        verbose_name_plural = 'Movimentações Diárias'
        ordering = ['data']

    def __str__(self):
        return f'{self.data} {self.armazem} → {self.fabrica}: {self.quantidade_ton}t'


class LogExecucao(CooperativaScopedModel):
    """`cenario` é nullable de propósito -- diferente de `CenarioScopedModel`
    (não herda dele). NULL representa uma execução rodada contra o cenário
    oficial. Ver ADR 0005."""

    class Status(models.TextChoices):
        EM_ANDAMENTO = 'em_andamento', 'Em andamento'
        SUCESSO = 'sucesso', 'Sucesso'
        ERRO = 'erro', 'Erro'

    cenario = models.ForeignKey(Cenario, on_delete=models.CASCADE, null=True, blank=True)
    data_execucao = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=50, blank=True, default='', choices=Status.choices)
    mensagem = models.CharField(max_length=500, blank=True, default='')
    duracao_segundos = models.FloatField(null=True, blank=True)
    dias_simulados = models.IntegerField(null=True, blank=True)

    class Meta:
        verbose_name = 'Log de Execução'
        verbose_name_plural = 'Logs de Execução'
        ordering = ['-data_execucao']

    def __str__(self):
        return f'{self.data_execucao:%Y-%m-%d %H:%M} — {self.status}'

    def clean(self):
        super().clean()
        if self.cenario_id is not None and self.cenario.cooperativa_id != self.cooperativa_id:
            raise ValidationError('cooperativa não corresponde à cooperativa do cenario.')


class ResumoMensalFabrica(CenarioScopedModel):
    mes = models.CharField(max_length=7)  # 'YYYY-MM'
    fabrica = models.ForeignKey(Fabrica, on_delete=models.CASCADE)
    rec_produtor = models.FloatField(default=0)
    rec_transbordo = models.FloatField(default=0)
    esmagado = models.FloatField(default=0)
    saldo_estoque = models.FloatField(default=0)
    capacidade_estatica = models.FloatField(default=0)
    excedente = models.FloatField(default=0)

    class Meta:
        verbose_name = 'Resumo Mensal de Fábrica'
        verbose_name_plural = 'Resumos Mensais de Fábrica'

    def __str__(self):
        return f'{self.fabrica} — {self.mes}'


class ResumoMensalArmazem(CenarioScopedModel):
    mes = models.CharField(max_length=7)  # 'YYYY-MM'
    armazem = models.ForeignKey(Armazem, on_delete=models.CASCADE)
    rec_produtor = models.FloatField(default=0)
    envio_transbordo = models.FloatField(default=0)
    vendas = models.FloatField(default=0)
    saldo_estoque = models.FloatField(default=0)
    capacidade_estatica = models.FloatField(default=0)
    excedente = models.FloatField(default=0)

    class Meta:
        verbose_name = 'Resumo Mensal de Armazém'
        verbose_name_plural = 'Resumos Mensais de Armazém'

    def __str__(self):
        return f'{self.armazem} — {self.mes}'


class ConversaIA(CooperativaScopedModel):
    """Histórico persistido de uma conversa com o Assistente de IA, por
    cenário e por usuário. Ver Fase 9b."""

    cenario = models.ForeignKey(
        'simulacao.Cenario', on_delete=models.CASCADE, related_name='conversas_ia',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversas_ia',
    )
    titulo = models.CharField(max_length=120, blank=True)
    mensagens = models.JSONField(default=list)
    ativa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Conversa IA'
        verbose_name_plural = 'Conversas IA'
        ordering = ['-updated_at']

    def __str__(self):
        return self.titulo or f'Conversa {self.pk}'

    def adicionar(self, papel: str, conteudo: str) -> None:
        self.mensagens.append({
            'papel': papel,
            'conteudo': conteudo,
            'ts': timezone.now().isoformat(),
        })
