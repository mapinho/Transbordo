"""Importação de dados de cenário a partir de uma pasta .xlsx de cinco abas.

`analisar` lê e classifica sem escrever nada; `aplicar` grava. A fronteira
existe para que a pré-visualização seja confiável e para que quase toda a
lógica seja testável com uma pasta montada em memória. Ver
docs/superpowers/specs/2026-08-25-carga-de-dados-design.md.
"""
from dataclasses import dataclass, field

from openpyxl import load_workbook

from apps.simulacao.models import Armazem, Fabrica

ABA_FABRICAS = 'Fábricas'
ABA_ARMAZENS = 'Armazéns'
ABA_ROTAS = 'Rotas'
ABA_PREVISOES = 'Previsões'
ABA_SAFRAS = 'Safras'

# A ordem É a ordem de dependência: Rotas, Previsões e Safras resolvem nomes
# contra o que Fábricas e Armazéns criaram antes delas.
ABAS_NA_ORDEM = [ABA_FABRICAS, ABA_ARMAZENS, ABA_ROTAS, ABA_PREVISOES, ABA_SAFRAS]

COLUNAS_POR_ABA = {
    ABA_FABRICAS: [
        'nome', 'capacidade_estatica', 'capacidade_esmagamento_diaria',
        'capacidade_recebimento_diaria', 'limite_caminhoes',
        'carga_media_caminhao', 'estoque_inicial',
    ],
    ABA_ARMAZENS: [
        'nome', 'capacidade_estatica', 'capacidade_expedicao_diaria', 'estoque_inicial',
    ],
    ABA_ROTAS: [
        'origem', 'destino', 'distancia_km', 'custo_frete_ton', 'custo_frete_entressafra',
    ],
    ABA_PREVISOES: ['entidade', 'mes_referencia', 'recebimento_produtor', 'vendas'],
    ABA_SAFRAS: ['unidade', 'data_inicio', 'data_fim'],
}

# Numéricos obrigatórios: célula em branco rejeita a linha. Espelha
# FABRICA/ARMAZEM_CAMPOS_NUMERICOS_OBRIGATORIOS do data_loader.py legado -- é a
# correção do bug A8 da Fase 1, em que NaN do pandas chegava ao Postgres como
# número válido.
OBRIGATORIOS_POR_ABA = {
    ABA_FABRICAS: COLUNAS_POR_ABA[ABA_FABRICAS][1:],
    ABA_ARMAZENS: COLUNAS_POR_ABA[ABA_ARMAZENS][1:],
}


@dataclass
class LinhaRejeitada:
    aba: str
    linha: int  # número como aparece no Excel: o cabeçalho é 1
    motivo: str
    valores: dict


@dataclass
class ResumoAba:
    aba: str
    criar: int = 0
    atualizar: int = 0
    rejeitadas: list = field(default_factory=list)


@dataclass
class Relatorio:
    abas: list = field(default_factory=list)
    erro_estrutural: str = None

    @property
    def tem_erro_estrutural(self):
        return self.erro_estrutural is not None

    @property
    def total_criar(self):
        return sum(a.criar for a in self.abas)

    @property
    def total_atualizar(self):
        return sum(a.atualizar for a in self.abas)

    @property
    def total_rejeitadas(self):
        return sum(len(a.rejeitadas) for a in self.abas)

    def resumo(self, nome_aba):
        for a in self.abas:
            if a.aba == nome_aba:
                return a
        return None


def _erro(mensagem):
    return Relatorio(abas=[ResumoAba(aba=n) for n in ABAS_NA_ORDEM], erro_estrutural=mensagem)


def _normalizar(valor):
    return str(valor).strip().lower() if valor is not None else ''


def _ler_abas(arquivo):
    """Devolve (abas, erro). abas = {nome: [(linha_excel, {coluna: valor})]}."""
    try:
        wb = load_workbook(arquivo, data_only=True, read_only=True)
    except Exception:  # noqa: BLE001 -- openpyxl levanta tipos variados
        return None, 'Arquivo não pôde ser lido como .xlsx.'

    presentes = [n for n in ABAS_NA_ORDEM if n in wb.sheetnames]
    if not presentes:
        return None, 'Nenhuma aba reconhecida. Esperadas: ' + ', '.join(ABAS_NA_ORDEM) + '.'

    abas = {n: [] for n in ABAS_NA_ORDEM}
    for nome in presentes:
        ws = wb[nome]
        linhas = ws.iter_rows(values_only=True)
        try:
            cabecalho = [_normalizar(c) for c in next(linhas)]
        except StopIteration:
            continue  # aba presente mas totalmente vazia: nada a importar
        faltando = [c for c in COLUNAS_POR_ABA[nome] if c not in cabecalho]
        if faltando:
            return None, (
                f"Aba '{nome}': coluna(s) ausente(s) no cabeçalho: {', '.join(faltando)}."
            )
        for numero, valores in enumerate(linhas, start=2):
            if all(v is None for v in valores):
                continue
            abas[nome].append((numero, dict(zip(cabecalho, valores))))
    return abas, None


def _numero(valores, coluna):
    """Devolve (numero, erro). Célula em branco e valor não numérico são erro."""
    bruto = valores.get(coluna)
    if bruto is None or (isinstance(bruto, str) and not bruto.strip()):
        return None, f'{coluna} em branco'
    try:
        return float(bruto), None
    except (TypeError, ValueError):
        return None, f'{coluna} não é um número: {bruto!r}'


def _texto(valores, coluna):
    bruto = valores.get(coluna)
    if bruto is None:
        return None
    return str(bruto).strip() or None


def _analisar_unidades(aba, linhas, existentes, resumo):
    """Fábricas e Armazéns: mesma forma, só muda a lista de obrigatórios.

    Devolve o conjunto de nomes que a pasta vai criar ou atualizar, para as
    abas seguintes resolverem contra ele.
    """
    nomes = set()
    for numero, valores in linhas:
        nome = _texto(valores, 'nome')
        if not nome:
            resumo.rejeitadas.append(LinhaRejeitada(aba, numero, 'nome em branco', valores))
            continue
        erros = []
        for coluna in OBRIGATORIOS_POR_ABA[aba]:
            _, erro = _numero(valores, coluna)
            if erro:
                erros.append(erro)
        if erros:
            resumo.rejeitadas.append(LinhaRejeitada(aba, numero, '; '.join(erros), valores))
            continue
        if nome in existentes:
            resumo.atualizar += 1
        else:
            resumo.criar += 1
        nomes.add(nome)
    return nomes


def analisar(arquivo, cenario):
    """Lê a pasta e classifica cada linha. NUNCA escreve.

    `cenario` pode ser None (bootstrap: o cenário ainda não existe). Nesse caso
    o lado-banco da resolução é vazio -- tudo é criação, e os nomes resolvem
    apenas contra a própria pasta.
    """
    abas, erro = _ler_abas(arquivo)
    if erro:
        return _erro(erro)

    if cenario is not None:
        fabricas_no_banco = set(
            Fabrica.all_cooperativas.filter(cenario=cenario).values_list('nome', flat=True)
        )
        armazens_no_banco = set(
            Armazem.all_cooperativas.filter(cenario=cenario).values_list('nome', flat=True)
        )
    else:
        fabricas_no_banco = set()
        armazens_no_banco = set()

    relatorio = Relatorio(abas=[ResumoAba(aba=n) for n in ABAS_NA_ORDEM])

    _analisar_unidades(
        ABA_FABRICAS, abas[ABA_FABRICAS], fabricas_no_banco, relatorio.resumo(ABA_FABRICAS),
    )
    _analisar_unidades(
        ABA_ARMAZENS, abas[ABA_ARMAZENS], armazens_no_banco, relatorio.resumo(ABA_ARMAZENS),
    )

    return relatorio
