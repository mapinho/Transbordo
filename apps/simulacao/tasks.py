from procrastinate.contrib.django import app

from apps.simulacao import engine
from apps.simulacao.models import LogExecucao


@app.task
def executar_simulacao(log_id, cenario_id, data_inicio, data_fim, estrategia):
    """Wrapper assíncrono de `engine.simular_periodo` -- a lógica de
    otimização não é tocada. `log_id` referencia o `LogExecucao` marcador
    de "em andamento" criado por quem chamou `.defer()` (a view); em caso
    de sucesso ele é descartado porque `simular_periodo` já cria seu
    próprio `LogExecucao(status='sucesso')` ao final. Em caso de falha,
    esse mesmo marcador vira o registro de erro -- `simular_periodo` não
    grava nada no caminho de exceção."""
    try:
        engine.simular_periodo(data_inicio, data_fim, cenario_id=cenario_id, estrategia=estrategia)
    except Exception as exc:
        LogExecucao.all_cooperativas.filter(id=log_id).update(
            status='erro', mensagem=str(exc)[:500],
        )
        raise
    else:
        LogExecucao.all_cooperativas.filter(id=log_id).delete()
