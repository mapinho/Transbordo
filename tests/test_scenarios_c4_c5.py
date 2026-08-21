import datetime
import unicodedata

import pytest

import scenarios
from models import Armazem, Cenario, Fabrica, SafraUnidade

# A byte-for-byte different (NFD, combining-accent) spelling of "Fábrica"
# that *looks* identical but fails a strict `== 'Fábrica'` (NFC) comparison.
# This models real-world data where the persisted entidade_tipo value for a
# factory is not the exact literal 'Fábrica' string (e.g. differing unicode
# normalization / encoding from import or legacy data).
FABRICA_TIPO_VARIANT = unicodedata.normalize("NFD", "Fábrica")


def test_clone_scenario_preserves_fabrica_safra_window(session, cenario, fabrica, armazem):
    """C4: cloning a SafraUnidade for a Fábrica must attach it to the cloned
    Fábrica's id (via fabrica_map), not silently to the armazem_map, even
    when the persisted entidade_tipo string is not byte-identical to the
    literal 'Fábrica' used elsewhere -- per the codebase-wide convention of
    checking `== 'Armazém'` first and defaulting to Fábrica otherwise."""
    assert FABRICA_TIPO_VARIANT != "Fábrica"  # sanity check on the fixture data

    # Add a second Armazém so that Fabrica.id and Armazem.id sequences diverge
    # after cloning (both start at 1, so without this the two candidate
    # "correct" ids could coincidentally collide and mask the bug).
    extra_armazem = Armazem(
        cenario_id=cenario.id,
        nome="Armazém Extra",
        capacidade_estatica=100,
        capacidade_expedicao_diaria=10,
        estoque_inicial=0,
    )
    session.add(extra_armazem)
    session.commit()

    safra = SafraUnidade(
        cenario_id=cenario.id,
        entidade_tipo=FABRICA_TIPO_VARIANT,
        entidade_id=fabrica.id,
        data_inicio=datetime.date(2026, 1, 15),
        data_fim=datetime.date(2026, 4, 15),
    )
    session.add(safra)
    session.commit()

    new_id = scenarios.clone_scenario(session, "Novo Nome", cenario.id)

    new_cenario = session.get(Cenario, new_id)
    assert new_cenario is not None

    cloned_fabrica = (
        session.query(Fabrica)
        .filter_by(cenario_id=new_id, nome=fabrica.nome)
        .first()
    )
    assert cloned_fabrica is not None

    cloned_safras = (
        session.query(SafraUnidade).filter_by(cenario_id=new_id).all()
    )
    assert len(cloned_safras) == 1
    cloned_safra = cloned_safras[0]
    assert cloned_safra.entidade_id == cloned_fabrica.id


def test_clone_scenario_is_atomic_on_failure(session, cenario, fabrica, armazem, monkeypatch):
    """C5: if cloning fails partway through, the whole operation must roll
    back, leaving no orphaned Cenario row behind."""

    original_query = session.query

    def failing_query(model, *args, **kwargs):
        # Force a failure during the "Clonar Rotas" phase, which runs after
        # Fábricas and Armazéns have already been cloned/flushed.
        from models import Rota

        if model is Rota:
            raise RuntimeError("forced failure during rota cloning")
        return original_query(model, *args, **kwargs)

    monkeypatch.setattr(session, "query", failing_query)

    with pytest.raises(RuntimeError):
        scenarios.clone_scenario(session, "Novo Nome", cenario.id)

    monkeypatch.undo()

    orphaned = session.query(Cenario).filter_by(nome="Novo Nome").count()
    assert orphaned == 0
