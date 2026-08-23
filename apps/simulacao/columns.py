"""Config explícito de colunas por grade Tabulator (ver spec
2026-08-23-fase5-ui-dados-cenarios-design.md, §4 -- não é introspecção
genérica do model, são grades fixas com necessidades diferentes o
bastante para não valer a abstração)."""

FABRICA_COLUMNS = [
    {"field": "id", "label": "ID", "type": "number", "editable": False, "visible": False},
    {"field": "nome", "label": "Fábrica", "type": "text", "editable": False},
    {"field": "capacidade_estatica", "label": "Capacidade Estática (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "capacidade_esmagamento_diaria", "label": "Esmagamento Diário (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "capacidade_recebimento_diaria", "label": "Recebimento Diário (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "limite_caminhoes", "label": "Limite de Caminhões", "type": "number", "editable": True, "decimals": 0},
    {"field": "carga_media_caminhao", "label": "Carga Média (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "estoque_inicial", "label": "Estoque Inicial (Ton)", "type": "number", "editable": True, "decimals": 1},
]
