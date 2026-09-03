import csv
import datetime
import io
import json
import secrets

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from procrastinate.exceptions import AlreadyEnqueued

from apps.core.models import Cooperativa
from apps.core.permissions import (
    requer_edicao_armazens,
    requer_edicao_fabricas,
    requer_membro_organizacao,
)
from apps.core.tenancy import cooperativa_id_do_request
from apps.simulacao import assistente, engine, estoque, resultados, services, tasks
from apps.simulacao.forms import EstoqueForm, ResultadosForm
from apps.simulacao.columns import (
    ARMAZEM_COLUMNS,
    FABRICA_COLUMNS,
    PREVISAO_ARMAZEM_COLUMNS,
    PREVISAO_FABRICA_COLUMNS,
    ROTA_COLUMNS,
    SAFRA_COLUMNS,
)
from apps.simulacao.models import (
    Armazem,
    Cenario,
    ConversaIA,
    Fabrica,
    LogExecucao,
    MovimentacaoDiaria,
    PrevisaoArmazem,
    PrevisaoFabrica,
    ResumoMensalArmazem,
    ResumoMensalFabrica,
    Rota,
    SafraUnidade,
)
from apps.simulacao.planilha import ABAS_NA_ORDEM, analisar, aplicar, gerar_template

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
ESTRATEGIAS = ['Econômico', 'Expedição', 'Segurança']
STALENESS_TIMEOUT = datetime.timedelta(minutes=30)


@login_required
@requer_membro_organizacao
def cenarios_list(request):
    cooperativa_id = cooperativa_id_do_request(request)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        origem_id = request.POST.get('origem_id')
        if nome and origem_id:
            services.clone_scenario(cooperativa_id, nome, int(origem_id))
        return redirect('simulacao:cenarios_list')

    cenarios = services.list_scenarios(cooperativa_id)
    context = {'cenarios': cenarios}
    template = 'simulacao/_cenarios_content.html' if request.htmx else 'simulacao/cenarios.html'
    return render(request, template, context)


@login_required
@requer_edicao_fabricas
def fabricas_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas = json.loads(request.POST.get('linhas_json', '[]'))
        try:
            _salvar_fabricas(cenario, linhas)
        except (ValueError, TypeError, Fabrica.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar fábricas: {exc}")

    fabricas = list(Fabrica.objects.filter(cenario_id=cenario.id).order_by('nome'))
    rows = [
        {
            "id": f.id, "nome": f.nome,
            "capacidade_estatica": f.capacidade_estatica,
            "capacidade_esmagamento_diaria": f.capacidade_esmagamento_diaria,
            "capacidade_recebimento_diaria": f.capacidade_recebimento_diaria,
            "limite_caminhoes": f.limite_caminhoes,
            "carga_media_caminhao": f.carga_media_caminhao,
            "estoque_inicial": f.estoque_inicial,
        }
        for f in fabricas
    ]
    context = {"cenario": cenario, "active": "fabricas", "columns": FABRICA_COLUMNS, "rows": rows}
    template = 'simulacao/_fabricas_content.html' if request.htmx else 'simulacao/fabricas.html'
    return render(request, template, context)


def _salvar_fabricas(cenario, linhas):
    with transaction.atomic():
        for linha in linhas:
            fabrica_id = linha.get('id')
            if not fabrica_id:
                continue
            fabrica = Fabrica.objects.get(id=fabrica_id, cenario_id=cenario.id)
            fabrica.capacidade_estatica = float(linha['capacidade_estatica'])
            fabrica.capacidade_esmagamento_diaria = float(linha['capacidade_esmagamento_diaria'])
            fabrica.capacidade_recebimento_diaria = float(linha['capacidade_recebimento_diaria'])
            fabrica.limite_caminhoes = int(linha['limite_caminhoes'])
            fabrica.carga_media_caminhao = float(linha['carga_media_caminhao'])
            fabrica.estoque_inicial = float(linha['estoque_inicial'])
            fabrica.full_clean()
            fabrica.save()


@login_required
@requer_edicao_armazens
def armazens_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas = json.loads(request.POST.get('linhas_json', '[]'))
        try:
            _salvar_armazens(cenario, linhas)
        except (ValueError, TypeError, Armazem.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar armazéns: {exc}")

    armazens = list(Armazem.objects.filter(cenario_id=cenario.id).order_by('nome'))
    rows = [
        {
            "id": a.id, "nome": a.nome,
            "capacidade_estatica": a.capacidade_estatica,
            "capacidade_expedicao_diaria": a.capacidade_expedicao_diaria,
            "estoque_inicial": a.estoque_inicial,
        }
        for a in armazens
    ]
    context = {"cenario": cenario, "active": "armazens", "columns": ARMAZEM_COLUMNS, "rows": rows}
    template = 'simulacao/_armazens_content.html' if request.htmx else 'simulacao/armazens.html'
    return render(request, template, context)


def _salvar_armazens(cenario, linhas):
    with transaction.atomic():
        for linha in linhas:
            armazem_id = linha.get('id')
            if armazem_id:
                armazem = Armazem.objects.get(id=armazem_id, cenario_id=cenario.id)
            else:
                if not linha.get('nome'):
                    continue
                armazem = Armazem(cooperativa_id=cenario.cooperativa_id, cenario_id=cenario.id)
            armazem.nome = linha['nome']
            armazem.capacidade_estatica = float(linha['capacidade_estatica'])
            armazem.capacidade_expedicao_diaria = float(linha['capacidade_expedicao_diaria'])
            armazem.estoque_inicial = float(linha.get('estoque_inicial') or 0)
            armazem.full_clean()
            armazem.save()


@login_required
@requer_membro_organizacao
def rotas_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas = json.loads(request.POST.get('linhas_json', '[]'))
        try:
            _salvar_rotas(cenario, linhas)
        except (ValueError, TypeError, Rota.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar rotas: {exc}")

    rotas = list(Rota.objects.filter(cenario_id=cenario.id).select_related('armazem', 'fabrica'))
    rows = [
        {
            "id": r.id, "origem": r.armazem.nome, "destino": r.fabrica.nome,
            "distancia_km": r.distancia_km,
            "custo_frete_ton": r.custo_frete_ton,
            "custo_frete_entressafra": r.custo_frete_entressafra,
        }
        for r in rotas
    ]
    context = {"cenario": cenario, "active": "rotas", "columns": ROTA_COLUMNS, "rows": rows}
    template = 'simulacao/_rotas_content.html' if request.htmx else 'simulacao/rotas.html'
    return render(request, template, context)


def _salvar_rotas(cenario, linhas):
    with transaction.atomic():
        for linha in linhas:
            rota_id = linha.get('id')
            if not rota_id:
                continue
            rota = Rota.objects.get(id=rota_id, cenario_id=cenario.id)
            rota.distancia_km = float(linha['distancia_km'])
            rota.custo_frete_ton = float(linha['custo_frete_ton'])
            rota.custo_frete_entressafra = float(linha['custo_frete_entressafra'])
            rota.full_clean()
            rota.save()


@login_required
@requer_membro_organizacao
def previsoes_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas_fabrica = json.loads(request.POST.get('linhas_fabrica_json', '[]'))
        linhas_armazem = json.loads(request.POST.get('linhas_armazem_json', '[]'))
        try:
            _salvar_previsoes(cenario, linhas_fabrica, linhas_armazem)
        except (ValueError, TypeError, PrevisaoFabrica.DoesNotExist, PrevisaoArmazem.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar previsões: {exc}")

    previsoes_fab = list(
        PrevisaoFabrica.objects.filter(fabrica__cenario_id=cenario.id).select_related('fabrica')
    )
    previsoes_arm = list(
        PrevisaoArmazem.objects.filter(armazem__cenario_id=cenario.id).select_related('armazem')
    )
    rows_fabrica = [
        {
            "id": p.id, "fabrica": p.fabrica.nome, "mes_referencia": p.mes_referencia.strftime('%Y-%m'),
            "recebimento_produtor": p.recebimento_produtor, "vendas": p.vendas,
        }
        for p in previsoes_fab
    ]
    rows_armazem = [
        {
            "id": p.id, "armazem": p.armazem.nome, "mes_referencia": p.mes_referencia.strftime('%Y-%m'),
            "recebimento_produtor": p.recebimento_produtor, "vendas": p.vendas,
        }
        for p in previsoes_arm
    ]
    context = {
        "cenario": cenario, "active": "previsoes",
        "columns_fabrica": PREVISAO_FABRICA_COLUMNS, "rows_fabrica": rows_fabrica,
        "columns_armazem": PREVISAO_ARMAZEM_COLUMNS, "rows_armazem": rows_armazem,
    }
    template = 'simulacao/_previsoes_content.html' if request.htmx else 'simulacao/previsoes.html'
    return render(request, template, context)


def _salvar_previsoes(cenario, linhas_fabrica, linhas_armazem):
    with transaction.atomic():
        for linha in linhas_fabrica:
            previsao_id = linha.get('id')
            if not previsao_id:
                continue
            previsao = PrevisaoFabrica.objects.get(id=previsao_id, fabrica__cenario_id=cenario.id)
            previsao.recebimento_produtor = float(linha['recebimento_produtor'])
            previsao.vendas = float(linha['vendas'])
            previsao.full_clean()
            previsao.save()
        for linha in linhas_armazem:
            previsao_id = linha.get('id')
            if not previsao_id:
                continue
            previsao = PrevisaoArmazem.objects.get(id=previsao_id, armazem__cenario_id=cenario.id)
            previsao.recebimento_produtor = float(linha['recebimento_produtor'])
            previsao.vendas = float(linha['vendas'])
            previsao.full_clean()
            previsao.save()


@login_required
@requer_membro_organizacao
def safras_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas = json.loads(request.POST.get('linhas_json', '[]'))
        try:
            _salvar_safras(cenario, linhas)
        except (ValueError, TypeError, SafraUnidade.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar datas de safra: {exc}")

    safras = list(SafraUnidade.objects.filter(cenario_id=cenario.id))
    armazem_ids = {s.entidade_id for s in safras if s.entidade_tipo == 'Armazém'}
    fabrica_ids = {s.entidade_id for s in safras if s.entidade_tipo != 'Armazém'}
    armazens_map = {a.id: a.nome for a in Armazem.objects.filter(id__in=armazem_ids)} if armazem_ids else {}
    fabricas_map = {f.id: f.nome for f in Fabrica.objects.filter(id__in=fabrica_ids)} if fabrica_ids else {}

    rows = []
    for s in safras:
        if s.entidade_tipo == 'Armazém':
            unidade_nome = armazens_map.get(s.entidade_id, 'N/A')
        else:
            unidade_nome = fabricas_map.get(s.entidade_id, 'N/A')
        rows.append({
            "id": s.id, "tipo": s.entidade_tipo, "unidade": unidade_nome,
            "data_inicio": s.data_inicio.strftime('%Y-%m-%d'),
            "data_fim": s.data_fim.strftime('%Y-%m-%d'),
        })

    context = {"cenario": cenario, "active": "safras", "columns": SAFRA_COLUMNS, "rows": rows}
    template = 'simulacao/_safras_content.html' if request.htmx else 'simulacao/safras.html'
    return render(request, template, context)


def _salvar_safras(cenario, linhas):
    with transaction.atomic():
        for linha in linhas:
            safra_id = linha.get('id')
            if not safra_id:
                continue
            safra = SafraUnidade.objects.get(id=safra_id, cenario_id=cenario.id)
            safra.data_inicio = datetime.date.fromisoformat(linha['data_inicio'])
            safra.data_fim = datetime.date.fromisoformat(linha['data_fim'])
            safra.full_clean()
            safra.save()


def _caminho_da_carga(token):
    return f'carga/{token}.xlsx'


@login_required
@requer_membro_organizacao
def carga_template(request):
    return FileResponse(
        gerar_template(), as_attachment=True,
        filename='modelo-carga-comigo.xlsx', content_type=XLSX,
    )


@login_required
@requer_membro_organizacao
def carga_upload(request):
    cooperativa_id = cooperativa_id_do_request(request)
    cenarios = list(Cenario.all_cooperativas.filter(cooperativa_id=cooperativa_id))

    if request.method == 'POST':
        arquivo = request.FILES.get('arquivo')
        if not arquivo:
            return HttpResponseBadRequest('Nenhum arquivo enviado.')

        cenario_id = request.POST.get('cenario_id')
        nome_novo = (request.POST.get('nome_novo') or '').strip()
        max_nome = Cenario._meta.get_field('nome').max_length
        if cenario_id:
            # Filtrar pela cooperativa: um cenário alheio não é distinguível
            # de um inexistente.
            get_object_or_404(
                Cenario.all_cooperativas, id=cenario_id, cooperativa_id=cooperativa_id,
            )
        elif not nome_novo:
            return HttpResponseBadRequest(
                'Informe um cenário existente ou o nome de um novo.'
            )
        elif len(nome_novo) > max_nome:
            return HttpResponseBadRequest(
                f'O nome do cenário não pode ter mais de {max_nome} caracteres.'
            )

        anterior = request.session.get('carga')
        if anterior:
            default_storage.delete(_caminho_da_carga(anterior['token']))

        token = secrets.token_urlsafe(16)
        default_storage.save(_caminho_da_carga(token), arquivo)
        request.session['carga'] = {
            'token': token,
            'cenario_id': int(cenario_id) if cenario_id else None,
            'nome_novo': nome_novo or None,
        }
        return redirect('simulacao:carga_preview', token=token)

    context = {'cenarios': cenarios, 'abas': ABAS_NA_ORDEM}
    template = 'simulacao/_carga_content.html' if request.htmx else 'simulacao/carga.html'
    return render(request, template, context)


@login_required
@requer_membro_organizacao
def carga_preview(request, token):
    guardado = request.session.get('carga')
    if not guardado or guardado['token'] != token:
        raise Http404('Carga não encontrada.')

    cooperativa_id = cooperativa_id_do_request(request)
    cenario = None
    if guardado['cenario_id']:
        cenario = get_object_or_404(
            Cenario.all_cooperativas,
            id=guardado['cenario_id'], cooperativa_id=cooperativa_id,
        )

    caminho = _caminho_da_carga(token)

    if request.method == 'POST':
        with default_storage.open(caminho, 'rb') as arquivo:
            try:
                _relatorio, gravado = aplicar(
                    arquivo, cenario=cenario,
                    cooperativa=Cooperativa.objects.get(id=cooperativa_id),
                    nome_novo=guardado['nome_novo'],
                )
            except (ValueError, ValidationError) as erro:
                mensagem = '; '.join(erro.messages) if isinstance(erro, ValidationError) else str(erro)
                return HttpResponseBadRequest(mensagem)
        default_storage.delete(caminho)
        del request.session['carga']
        if gravado is None:
            return HttpResponseBadRequest('A planilha não pôde ser aplicada.')
        return redirect('simulacao:fabricas_grid', cenario_id=gravado.id)

    with default_storage.open(caminho, 'rb') as arquivo:
        relatorio = analisar(arquivo, cenario)

    context = {
        'relatorio': relatorio, 'token': token,
        'cenario': cenario, 'nome_novo': guardado['nome_novo'],
    }
    template = (
        'simulacao/_carga_preview_content.html' if request.htmx
        else 'simulacao/carga_preview.html'
    )
    return render(request, template, context)


@login_required
@requer_membro_organizacao
def simulacao_tab(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    inicio_sugerido, fim_sugerido = engine.obter_range_previsoes(cenario_id=cenario.id)
    log_atual = LogExecucao.objects.filter(cenario_id=cenario.id).order_by('-id').first()
    context = {
        "cenario": cenario, "active": "simulacao",
        "inicio_sugerido": inicio_sugerido, "fim_sugerido": fim_sugerido,
        "estrategias": ESTRATEGIAS, "log_atual": log_atual,
    }
    template = 'simulacao/_simulacao_content.html' if request.htmx else 'simulacao/simulacao.html'
    return render(request, template, context)


@login_required
@requer_membro_organizacao
@require_POST
def simulacao_executar(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    data_inicio = request.POST.get('data_inicio', '')
    data_fim = request.POST.get('data_fim', '')
    estrategia = request.POST.get('estrategia', '')
    if not data_inicio or not data_fim:
        return HttpResponseBadRequest('Informe o período da simulação.')
    if estrategia not in ESTRATEGIAS:
        return HttpResponseBadRequest('Estratégia inválida.')

    em_andamento = (
        LogExecucao.objects.filter(cenario_id=cenario.id, status=LogExecucao.Status.EM_ANDAMENTO)
        .order_by('-id').first()
    )
    if em_andamento is not None:
        if timezone.now() - em_andamento.data_execucao < STALENESS_TIMEOUT:
            return HttpResponseBadRequest(
                'Já existe uma simulação em andamento para este cenário.'
            )
        em_andamento.status = LogExecucao.Status.ERRO
        em_andamento.mensagem = 'Execução interrompida — worker inativo.'
        em_andamento.save(update_fields=['status', 'mensagem'])

    log = LogExecucao.objects.create(
        cooperativa_id=cenario.cooperativa_id, cenario_id=cenario.id,
        status=LogExecucao.Status.EM_ANDAMENTO,
    )
    lock = f'simulacao-cenario-{cenario.id}'
    try:
        tasks.executar_simulacao.configure(lock=lock, queueing_lock=lock).defer(
            log_id=log.id, cenario_id=cenario.id,
            data_inicio=data_inicio, data_fim=data_fim, estrategia=estrategia,
        )
    except AlreadyEnqueued:
        log.delete()
        return HttpResponseBadRequest('Já existe uma simulação em andamento para este cenário.')

    return _render_simulacao_status(request, cenario)


@login_required
@requer_membro_organizacao
def simulacao_status(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    return _render_simulacao_status(request, cenario)


def _render_simulacao_status(request, cenario):
    log_atual = LogExecucao.objects.filter(cenario_id=cenario.id).order_by('-id').first()
    context = {"cenario": cenario, "log_atual": log_atual}
    return render(request, 'simulacao/_simulacao_status.html', context)


def _conversa_ativa(cenario, usuario):
    conversa = (
        ConversaIA.objects.filter(cenario=cenario, usuario=usuario, ativa=True)
        .order_by('-updated_at').first()
    )
    if conversa is None:
        conversa = ConversaIA.objects.create(
            cooperativa_id=cenario.cooperativa_id, cenario=cenario, usuario=usuario,
        )
    return conversa


def _assistente_context(request, cenario):
    return {
        'cenario': cenario,
        'active': 'assistente',
        'conversa': _conversa_ativa(cenario, request.user),
        'conversas': ConversaIA.objects.filter(
            cenario=cenario, usuario=request.user, ativa=False,
        ).order_by('-updated_at')[:20],
        'assistente_disponivel': bool(settings.GEMINI_API_KEY),
    }


@login_required
@requer_membro_organizacao
def assistente_tab(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    context = _assistente_context(request, cenario)
    template = 'simulacao/_assistente_content.html' if request.htmx else 'simulacao/assistente.html'
    return render(request, template, context)


@login_required
@requer_membro_organizacao
@require_POST
def assistente_enviar(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    mensagem = request.POST.get('mensagem', '').strip()
    conversa = _conversa_ativa(cenario, request.user)
    if mensagem:
        assistente.responder(conversa, mensagem)
    return render(request, 'simulacao/_assistente_transcript.html',
                  {'conversa': conversa, 'cenario': cenario})


@login_required
@requer_membro_organizacao
@require_POST
def assistente_nova(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    ConversaIA.objects.filter(cenario=cenario, usuario=request.user, ativa=True).update(ativa=False)
    return render(request, 'simulacao/_assistente_content.html',
                  _assistente_context(request, cenario))


def _filtros_avancados(filtros):
    """`(ativos, count)` — quantos dos filtros de mês/data/unidade estão preenchidos."""
    campos = ("mes_de", "mes_ate", "data_de", "data_ate", "armazem_ids", "fabrica_ids")
    n = sum(1 for c in campos if filtros.get(c))
    return n > 0, n


def _resultados_params(request, cenario):
    """Parseia os parâmetros compartilhados por resultados_tab e resultados_export.
    `comparar_id` é int | None (parâmetro não-numérico é descartado)."""
    form = ResultadosForm(request.GET or None, cenario=cenario)
    form.is_valid()
    filtros = form.filtros_limpos() if form.is_bound else {
        "data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []}
    periodo, agrupar = resultados.normalizar_visao(
        request.GET.get("periodo"), request.GET.get("agrupar"))
    comparar_raw = request.GET.get("comparar") or ""
    try:
        comparar_id = int(comparar_raw) if comparar_raw else None
    except (TypeError, ValueError):
        comparar_id = None
    return form, filtros, periodo, agrupar, comparar_id


def _fmt_delta_export(v):
    """Δ% (`float | "novo" | None`) formatado em pt-BR para célula de export:
    `+3,4%` / `-1,2%` / `novo` / `""`."""
    if v == "novo":
        return "novo"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{v:+.1f}%".replace(".", ",")
    return ""


def _resultados_template(request, tem_dados):
    """Escolhe a parcial a renderizar pelo header HX-Target (django-htmx)."""
    if not request.htmx:
        return 'simulacao/resultados.html'
    alvo = request.htmx.target
    if not tem_dados:
        return 'simulacao/_resultados_content.html'
    if alvo == 'resultados-tabela' or request.GET.get('parcial') == 'tabela':
        return 'simulacao/_resultados_tabela.html'
    if alvo == 'resultados-area':
        return 'simulacao/_resultados_area.html'
    return 'simulacao/_resultados_content.html'


@login_required
@requer_membro_organizacao
def resultados_tab(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    tem_resultado = MovimentacaoDiaria.objects.filter(cenario_id=cenario.id).exists()

    if not tem_resultado:
        ctx = {"cenario": cenario, "active": "resultados", "tem_resultado": False}
        return render(request, _resultados_template(request, tem_dados=False), ctx)

    coop_id = cooperativa_id_do_request(request)
    form, filtros, periodo, agrupar, comparar_id = _resultados_params(request, cenario)
    comparar = str(comparar_id) if comparar_id else ""
    fa_ativos, fa_count = _filtros_avancados(filtros)
    try:
        pagina = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        pagina = 1

    dados = resultados.agregar(cenario.id, periodo, agrupar, filtros, pagina=pagina)
    card = resultados.totais_com_delta(cenario.id, comparar_id, filtros)
    grafico = resultados.dados_grafico(
        cenario.id, periodo, agrupar, filtros, comparar_id)
    if comparar_id:
        dados = resultados.aplicar_comparacao(dados, comparar_id, periodo, agrupar, filtros)

    qs = request.GET.copy()
    qs.pop("page", None)
    qs.pop("parcial", None)
    ctx = {
        "cenario": cenario, "active": "resultados", "tem_resultado": True,
        "form": form, "periodo": periodo, "agrupar": agrupar, "comparar": comparar,
        "dados": dados, "card": card, "grafico": grafico,
        "comparaveis": resultados.cenarios_comparaveis(cenario.id, coop_id),
        "periodos": resultados.ROTULOS_PERIODO, "agrupamentos": resultados.ROTULOS_AGRUPAR,
        "querystring": qs.urlencode(),
        "filtros_avancados_ativos": fa_ativos, "filtros_avancados_count": fa_count,
    }
    return render(request, _resultados_template(request, tem_dados=True), ctx)


@login_required
@requer_membro_organizacao
def resultados_export(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    formato = request.GET.get("formato", "xlsx")
    if formato not in ("xlsx", "csv"):
        return HttpResponseBadRequest("Formato inválido.")

    _form, filtros, periodo, agrupar, comparar_id = _resultados_params(request, cenario)

    try:
        dados = resultados.agregar(cenario.id, periodo, agrupar, filtros,
                                   pagina=None, limite=resultados.EXPORT_MAX)
    except resultados.RecorteGrandeDemais:
        return HttpResponseBadRequest("Refine os filtros para exportar.")
    if comparar_id:
        dados = resultados.aplicar_comparacao(dados, comparar_id, periodo, agrupar, filtros)

    colunas = dados["colunas"]
    com_delta = bool(dados.get("totais_delta"))

    def valor(linha, col):
        v = linha.get(col["key"])
        if col["tipo"] in ("data_dia", "data_mes"):
            return linha.get("dia")
        return v

    def cabecalho():
        out = []
        for c in colunas:
            out.append(c["label"])
            if com_delta and c.get("comparavel"):
                out.append(f'{c["label"]} \u0394%')
        return out

    def celulas(linha):
        out = []
        for c in colunas:
            out.append(valor(linha, c))
            if com_delta and c.get("comparavel"):
                out.append(_fmt_delta_export(linha.get(f'{c["key"]}_delta')))
        return out

    nome = f'resultados-{cenario.id}-{periodo}-{agrupar}-{timezone.now():%Y%m%d}'
    if formato == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.append(cabecalho())
        for linha in dados["linhas"]:
            ws.append(celulas(linha))
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return FileResponse(
            buf, as_attachment=True, filename=f'{nome}.xlsx', content_type=XLSX)

    buf = io.StringIO()
    buf.write("\ufeff")  # BOM UTF-8 (U+FEFF) para o Excel pt-BR abrir o CSV sem corromper acentos
    w = csv.writer(buf, delimiter=";")
    w.writerow(cabecalho())
    for linha in dados["linhas"]:
        row = []
        for v in celulas(linha):
            if isinstance(v, float):
                v = f"{v:.2f}".replace(".", ",")
            row.append(v)
        w.writerow(row)
    return FileResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        as_attachment=True, filename=f'{nome}.csv', content_type="text/csv")


def _estoque_params(request, cenario):
    """Parseia os parâmetros compartilhados por estoque_tab e estoque_export.
    `comparar_id` é int | None (parâmetro não-numérico é descartado)."""
    form = EstoqueForm(request.GET or None, cenario=cenario)
    form.is_valid()
    filtros = form.filtros_limpos() if form.is_bound else {
        "mes_de": "", "mes_ate": "", "armazem_ids": [], "fabrica_ids": []}
    visao = estoque.normalizar_visao(request.GET.get("visao"))
    comparar_raw = request.GET.get("comparar") or ""
    try:
        comparar_id = int(comparar_raw) if comparar_raw else None
    except (TypeError, ValueError):
        comparar_id = None
    return form, filtros, visao, comparar_id


def _estoque_template(request, tem_dados):
    """Escolhe a parcial a renderizar pelo header HX-Target (django-htmx)."""
    if not request.htmx:
        return 'simulacao/estoque.html'
    alvo = request.htmx.target
    if not tem_dados:
        return 'simulacao/_estoque_content.html'
    if alvo == 'estoque-tabela' or request.GET.get('parcial') == 'tabela':
        return 'simulacao/_estoque_tabela.html'
    if alvo == 'estoque-area':
        return 'simulacao/_estoque_area.html'
    return 'simulacao/_estoque_content.html'


@login_required
@requer_membro_organizacao
def estoque_tab(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    tem_estoque = (
        ResumoMensalArmazem.objects.filter(cenario_id=cenario.id).exists()
        or ResumoMensalFabrica.objects.filter(cenario_id=cenario.id).exists())

    if not tem_estoque:
        ctx = {"cenario": cenario, "active": "estoque", "tem_estoque": False}
        return render(request, _estoque_template(request, tem_dados=False), ctx)

    coop_id = cooperativa_id_do_request(request)
    form, filtros, visao, comparar_id = _estoque_params(request, cenario)
    comparar = str(comparar_id) if comparar_id else ""
    fa_ativos, fa_count = _filtros_avancados(filtros)
    try:
        pagina = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        pagina = 1

    dados = estoque.agregar(cenario.id, visao, filtros, pagina=pagina)
    card = estoque.card_com_delta(cenario.id, comparar_id, filtros)
    grafico = estoque.dados_grafico(cenario.id, filtros, comparar_id)
    if comparar_id:
        dados = estoque.aplicar_comparacao(dados, comparar_id, visao, filtros)

    qs = request.GET.copy()
    qs.pop("page", None)
    qs.pop("parcial", None)
    ctx = {
        "cenario": cenario, "active": "estoque", "tem_estoque": True,
        "form": form, "visao": visao, "comparar": comparar,
        "dados": dados, "card": card, "grafico": grafico,
        "comparaveis": estoque.cenarios_comparaveis(cenario.id, coop_id),
        "visoes": estoque.ROTULOS_VISAO,
        "querystring": qs.urlencode(),
        "filtros_avancados_ativos": fa_ativos, "filtros_avancados_count": fa_count,
    }
    return render(request, _estoque_template(request, tem_dados=True), ctx)


@login_required
@requer_membro_organizacao
def estoque_export(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    formato = request.GET.get("formato", "xlsx")
    if formato not in ("xlsx", "csv"):
        return HttpResponseBadRequest("Formato inválido.")

    _form, filtros, visao, comparar_id = _estoque_params(request, cenario)

    try:
        dados = estoque.agregar(cenario.id, visao, filtros,
                                pagina=None, limite=estoque.EXPORT_MAX)
    except estoque.RecorteGrandeDemais:
        return HttpResponseBadRequest("Refine os filtros para exportar.")
    if comparar_id:
        dados = estoque.aplicar_comparacao(dados, comparar_id, visao, filtros)

    colunas = dados["colunas"]
    com_delta = bool(dados.get("totais_delta"))

    def cabecalho():
        out = []
        for c in colunas:
            out.append(c["label"])
            if com_delta and c.get("comparavel"):
                out.append(f'{c["label"]} \u0394%')
        return out

    def celulas(linha):
        out = []
        for c in colunas:
            out.append(linha.get(c["key"]))
            if com_delta and c.get("comparavel"):
                out.append(_fmt_delta_export(linha.get(f'{c["key"]}_delta')))
        return out

    nome = f'estoque-{cenario.id}-{visao}-{timezone.now():%Y%m%d}'
    if formato == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.append(cabecalho())
        for linha in dados["linhas"]:
            ws.append(celulas(linha))
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return FileResponse(
            buf, as_attachment=True, filename=f'{nome}.xlsx', content_type=XLSX)

    buf = io.StringIO()
    buf.write("\ufeff")  # BOM UTF-8 (U+FEFF) para o Excel pt-BR abrir o CSV sem corromper acentos
    w = csv.writer(buf, delimiter=";")
    w.writerow(cabecalho())
    for linha in dados["linhas"]:
        row = []
        for v in celulas(linha):
            if isinstance(v, float):
                v = f"{v:.2f}".replace(".", ",")
            row.append(v)
        w.writerow(row)
    return FileResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        as_attachment=True, filename=f'{nome}.csv', content_type="text/csv")
