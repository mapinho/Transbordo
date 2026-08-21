import datetime

from sqlalchemy.orm import Session as SASession

import scenarios
from models import Armazem, Fabrica, PrevisaoArmazem, PrevisaoFabrica


def _build_source_scenario(session, cenario):
    """Creates 2 fabricas + 2 armazens under `cenario`, each with several
    PrevisaoFabrica/PrevisaoArmazem rows spread across different months."""
    fabricas = []
    for i in range(2):
        f = Fabrica(
            cenario_id=cenario.id,
            nome=f"Fábrica {i}",
            capacidade_estatica=10000,
            capacidade_esmagamento_diaria=500,
            capacidade_recebimento_diaria=600,
            limite_caminhoes=20,
            carga_media_caminhao=30,
            estoque_inicial=1000,
        )
        session.add(f)
        fabricas.append(f)
    session.commit()

    armazens = []
    for i in range(2):
        a = Armazem(
            cenario_id=cenario.id,
            nome=f"Armazém {i}",
            capacidade_estatica=5000,
            capacidade_expedicao_diaria=300,
            estoque_inicial=2000,
        )
        session.add(a)
        armazens.append(a)
    session.commit()

    for f_idx, f in enumerate(fabricas):
        # 2-3 previsao rows per fabrica, across different months.
        n_rows = 3 if f_idx == 0 else 2
        for m in range(n_rows):
            session.add(
                PrevisaoFabrica(
                    fabrica_id=f.id,
                    mes_referencia=datetime.date(2026, m + 1, 1),
                    recebimento_produtor=100.0 + f_idx * 10 + m,
                    vendas=50.0 + f_idx * 5 + m,
                )
            )

    for a_idx, a in enumerate(armazens):
        n_rows = 2 if a_idx == 0 else 3
        for m in range(n_rows):
            session.add(
                PrevisaoArmazem(
                    armazem_id=a.id,
                    mes_referencia=datetime.date(2026, m + 1, 1),
                    recebimento_produtor=200.0 + a_idx * 10 + m,
                    vendas=80.0 + a_idx * 5 + m,
                )
            )

    session.commit()
    return fabricas, armazens


# ---------------------------------------------------------------------------
# M8 - N+1 queries when cloning PrevisaoFabrica / PrevisaoArmazem rows
# ---------------------------------------------------------------------------

def test_clone_scenario_batches_previsao_queries(session, cenario, monkeypatch):
    """The actual red/green regression test: clone_scenario must issue
    exactly one batched query for PrevisaoFabrica and one for
    PrevisaoArmazem, instead of one query per cloned fabrica/armazem."""
    _build_source_scenario(session, cenario)

    original_query = SASession.query
    query_counts = {"PrevisaoFabrica": 0, "PrevisaoArmazem": 0}

    def counting_query(self, *args, **kwargs):
        for entity in args:
            if entity is PrevisaoFabrica:
                query_counts["PrevisaoFabrica"] += 1
            elif entity is PrevisaoArmazem:
                query_counts["PrevisaoArmazem"] += 1
        return original_query(self, *args, **kwargs)

    monkeypatch.setattr(SASession, "query", counting_query)

    scenarios.clone_scenario(session, "Clone Teste", cenario.id)

    assert query_counts["PrevisaoFabrica"] == 1, (
        f"Expected exactly 1 batched query for PrevisaoFabrica, got "
        f"{query_counts['PrevisaoFabrica']} -- looks like N+1 (bug M8)."
    )
    assert query_counts["PrevisaoArmazem"] == 1, (
        f"Expected exactly 1 batched query for PrevisaoArmazem, got "
        f"{query_counts['PrevisaoArmazem']} -- looks like N+1 (bug M8)."
    )


# ---------------------------------------------------------------------------
# M8 - characterization test: cloned previsão rows must be identical in
# content and correctly re-attached to the new fabrica/armazem ids, both
# before and after the batching fix.
# ---------------------------------------------------------------------------

def test_clone_scenario_clones_all_previsoes_correctly(session, cenario):
    fabricas, armazens = _build_source_scenario(session, cenario)

    source_fab_previsoes = (
        session.query(PrevisaoFabrica)
        .filter(PrevisaoFabrica.fabrica_id.in_([f.id for f in fabricas]))
        .all()
    )
    source_arm_previsoes = (
        session.query(PrevisaoArmazem)
        .filter(PrevisaoArmazem.armazem_id.in_([a.id for a in armazens]))
        .all()
    )

    new_id = scenarios.clone_scenario(session, "Clone Teste", cenario.id)

    new_fabricas = session.query(Fabrica).filter_by(cenario_id=new_id).all()
    new_armazens = session.query(Armazem).filter_by(cenario_id=new_id).all()

    name_to_new_fabrica_id = {f.nome: f.id for f in new_fabricas}
    name_to_new_armazem_id = {a.nome: a.id for a in new_armazens}

    new_fab_previsoes = (
        session.query(PrevisaoFabrica)
        .filter(PrevisaoFabrica.fabrica_id.in_(name_to_new_fabrica_id.values()))
        .all()
    )
    new_arm_previsoes = (
        session.query(PrevisaoArmazem)
        .filter(PrevisaoArmazem.armazem_id.in_(name_to_new_armazem_id.values()))
        .all()
    )

    # Total counts must match exactly -- nothing dropped, nothing duplicated.
    assert len(new_fab_previsoes) == len(source_fab_previsoes)
    assert len(new_arm_previsoes) == len(source_arm_previsoes)

    # Every source PrevisaoFabrica row must have a matching clone attached
    # to the correct new fabrica (same nome as its source parent).
    for old_f in fabricas:
        expected = {
            (p.mes_referencia, p.recebimento_produtor, p.vendas)
            for p in source_fab_previsoes
            if p.fabrica_id == old_f.id
        }
        new_fabrica_id = name_to_new_fabrica_id[old_f.nome]
        actual = {
            (p.mes_referencia, p.recebimento_produtor, p.vendas)
            for p in new_fab_previsoes
            if p.fabrica_id == new_fabrica_id
        }
        assert actual == expected

    # Same check for PrevisaoArmazem.
    for old_a in armazens:
        expected = {
            (p.mes_referencia, p.recebimento_produtor, p.vendas)
            for p in source_arm_previsoes
            if p.armazem_id == old_a.id
        }
        new_armazem_id = name_to_new_armazem_id[old_a.nome]
        actual = {
            (p.mes_referencia, p.recebimento_produtor, p.vendas)
            for p in new_arm_previsoes
            if p.armazem_id == new_armazem_id
        }
        assert actual == expected
