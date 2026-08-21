import data_loader


def test_get_engine_configures_explicit_pool_size_and_max_overflow(monkeypatch):
    """get_engine() must pass explicit pool_size/max_overflow to create_engine()
    instead of relying on SQLAlchemy's defaults (pool_size=5, max_overflow=10),
    so pool sizing is deliberately chosen and tunable for this app's expected
    concurrency (Fase 4 roadmap item, "Otimização -- Banco de dados")."""
    monkeypatch.delenv("STREAMLIT_RUNTIME_ENV", raising=False)
    monkeypatch.delenv("STREAMLIT_SERVER_PORT", raising=False)
    monkeypatch.setenv("DB_USER", "testuser")
    monkeypatch.setenv("DB_PASSWORD", "testpass")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "testdb")

    class _EmptySecrets(dict):
        def __bool__(self):
            return False

    monkeypatch.setattr(data_loader.st, "secrets", _EmptySecrets(), raising=False)

    captured = {}

    def _fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(data_loader, "create_engine", _fake_create_engine)

    engine, source = data_loader.get_engine.__wrapped__()

    assert captured["kwargs"]["pool_size"] == 10
    assert captured["kwargs"]["max_overflow"] == 20
    assert captured["kwargs"]["pool_pre_ping"] is True
