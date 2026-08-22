import datetime
import json
import logging

from apps.simulacao.models import SafraUnidade

# Ver ADR 0006: engine.py e services.py consultam via `all_cooperativas`
# (nunca `objects`, o TenantManager fail-closed) porque recebem o limite de
# tenant explicitamente via `cenario_id`/`scenario_id` -- exatamente como o
# codigo SQLAlchemy original ja funcionava, sem nocao de "cooperativa da
# sessao corrente". Confiar no contexto implicito de middleware aqui
# quebraria silenciosamente (queryset vazio) toda chamada feita fora de uma
# requisicao HTTP -- um worker Procrastinate futuro, um management command,
# ou os proprios testes deste arquivo.

_RESERVED_LOG_RECORD_ATTRS = frozenset({
    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
    'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
    'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
    'processName', 'process', 'taskName', 'message',
})


class JsonFormatter(logging.Formatter):
    """Formatter de logging que emite um objeto JSON por linha (structured
    logging). Porte 1:1 de `calculations.JsonFormatter` -- pura lógica de
    logging, sem dependência de ORM."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS:
                payload[key] = value

        if record.exc_info:
            payload['exc_info'] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logger = logging.getLogger(__name__)
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def _janela_safra_de_registro(safra, data):
    """Versão pura de `obter_janela_safra`: recebe o registro SafraUnidade já
    buscado (ou None) e resolve (na_safra, data_inicio, data_fim) sem tocar
    o banco. Porte 1:1 de `calculations._janela_safra_de_registro`."""
    if safra:
        data_inicio, data_fim = safra.data_inicio, safra.data_fim
    else:
        ano = data.year
        data_inicio = datetime.date(ano, 1, 15)
        data_fim = datetime.date(ano, 4, 15)

    na_safra = data_inicio <= data <= data_fim
    return na_safra, data_inicio, data_fim


def obter_janela_safra(entidade_tipo, entidade_id, data, cenario_id):
    """Determina a janela de safra de uma unidade e se `data` está dentro
    dela. Porte de `calculations.obter_janela_safra` -- assinatura igual,
    menos o parâmetro `session` (Django não tem sessão)."""
    safra = SafraUnidade.all_cooperativas.filter(
        cenario_id=cenario_id,
        entidade_tipo=entidade_tipo,
        entidade_id=entidade_id,
    ).first()
    return _janela_safra_de_registro(safra, data)


def _carregar_safras_por_armazem(cenario_id):
    """Pré-carrega todos os SafraUnidade de armazéns do cenário, indexados
    por armazem_id. Porte de `calculations._carregar_safras_por_armazem`."""
    rows = SafraUnidade.all_cooperativas.filter(
        cenario_id=cenario_id,
        entidade_tipo='Armazém',
    )
    return {r.entidade_id: r for r in rows}
