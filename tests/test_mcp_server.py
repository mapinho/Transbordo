import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


def _load_mcp(monkeypatch, url='http://localhost:8000/api/v1/', key='k-test'):
    monkeypatch.setenv('TRANSBORDO_API_URL', url)
    monkeypatch.setenv('TRANSBORDO_API_KEY', key)
    sys.modules.pop('mcp_server', None)
    import mcp_server
    return importlib.reload(mcp_server)


def test_missing_env_raises_at_import(monkeypatch):
    monkeypatch.delenv('TRANSBORDO_API_URL', raising=False)
    monkeypatch.delenv('TRANSBORDO_API_KEY', raising=False)
    sys.modules.pop('mcp_server', None)
    with pytest.raises(RuntimeError, match='TRANSBORDO_API'):
        import mcp_server  # noqa: F401


def test_base_url_strips_trailing_slash(monkeypatch):
    m = _load_mcp(monkeypatch, url='http://x/api/v1/')
    assert m.BASE_URL == 'http://x/api/v1'


def test_get_sends_key_header_and_drops_none_params(monkeypatch):
    m = _load_mcp(monkeypatch, key='segredo')
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{'id': 1}]
    with patch.object(m.httpx, 'get', return_value=resp) as mock_get:
        out = m._get('/cenarios/1/movimentacoes/', start_date='2026-01-01', end_date=None, limit=150)
    assert out == [{'id': 1}]
    args, kwargs = mock_get.call_args
    assert args[0] == 'http://localhost:8000/api/v1/cenarios/1/movimentacoes/'
    assert kwargs['headers']['X-API-Key'] == 'segredo'
    assert kwargs['params'] == {'start_date': '2026-01-01', 'limit': 150}


def test_get_maps_401_and_404(monkeypatch):
    m = _load_mcp(monkeypatch)
    for code, fragment in [(401, 'Chave de API'), (404, 'não encontrado')]:
        resp = MagicMock(status_code=code)
        resp.json.return_value = {'detail': 'x'}
        with patch.object(m.httpx, 'get', return_value=resp):
            with pytest.raises(m.ToolError, match=fragment):
                m._get('/cenarios/')


CASES = [
    ("list_scenarios", (), {}, "/cenarios/"),
    ("get_daily_movements", (7,), {}, "/cenarios/7/movimentacoes/"),
    ("get_monthly_summary", (7,), {}, "/cenarios/7/resumo-mensal/"),
    ("get_factories_summary", (7,), {}, "/cenarios/7/fabricas/resumo/"),
    ("get_warehouses_summary", (7,), {}, "/cenarios/7/armazens/resumo/"),
    ("compare_factories", (7,), {}, "/cenarios/7/fabricas/comparacao/"),
    ("compare_warehouses", (7,), {}, "/cenarios/7/armazens/comparacao/"),
    ("get_stock_excesses_report", (7,), {}, "/cenarios/7/alertas/excedentes/"),
    ("get_stock_ruptures_report", (7,), {}, "/cenarios/7/alertas/rupturas/"),
]


def _fn(m, nome):
    obj = getattr(m, nome)
    return obj.fn if hasattr(obj, "fn") else obj


@pytest.mark.parametrize("nome,args,kwargs,path", CASES)
def test_tool_hits_expected_endpoint(monkeypatch, nome, args, kwargs, path):
    m = _load_mcp(monkeypatch)
    resp = MagicMock(status_code=200)
    resp.json.return_value = []
    with patch.object(m.httpx, "get", return_value=resp) as mock_get:
        _fn(m, nome)(*args, **kwargs)
    assert mock_get.call_args[0][0] == f"http://localhost:8000/api/v1{path}"


def test_daily_movements_forwards_filters(monkeypatch):
    m = _load_mcp(monkeypatch)
    resp = MagicMock(status_code=200)
    resp.json.return_value = []
    with patch.object(m.httpx, "get", return_value=resp) as mock_get:
        _fn(m, "get_daily_movements")(7, start_date="2026-01-01", origin_id=3, limit=50)
    assert mock_get.call_args[1]["params"] == {"start_date": "2026-01-01", "origin_id": 3, "limit": 50}
