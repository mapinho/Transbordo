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

ROTA_COLUMNS = [
    {"field": "id", "label": "ID", "type": "number", "editable": False, "visible": False},
    {"field": "origem", "label": "Origem", "type": "text", "editable": False},
    {"field": "destino", "label": "Destino", "type": "text", "editable": False},
    {"field": "distancia_km", "label": "Distância (km)", "type": "number", "editable": True, "decimals": 1},
    {"field": "custo_frete_ton", "label": "Custo Safra (R$/Ton)", "type": "number", "editable": True, "decimals": 2},
    {"field": "custo_frete_entressafra", "label": "Custo Entressafra (R$/Ton)", "type": "number", "editable": True, "decimals": 2},
]

ARMAZEM_COLUMNS = [
    {"field": "id", "label": "ID", "type": "number", "editable": False, "visible": False},
    {"field": "nome", "label": "Armazém", "type": "text", "editable": True},
    {"field": "capacidade_estatica", "label": "Capacidade Estática (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "capacidade_expedicao_diaria", "label": "Expedição Diária (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "estoque_inicial", "label": "Estoque Inicial (Ton)", "type": "number", "editable": True, "decimals": 1},
]
