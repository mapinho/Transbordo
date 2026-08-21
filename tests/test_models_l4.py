from models import Rota


def test_deleting_fabrica_also_deletes_its_rotas(session, cenario, fabrica, armazem):
    """L4 (characterization/safety-net test, not a bug-repro test):

    Fabrica.rotas and Armazem.rotas both declare cascade="all, delete-orphan"
    pointing at the same Rota class -- a known SQLAlchemy anti-pattern, since
    delete-orphan requires a single unambiguous owning parent. There is no
    currently-observable wrong behavior here (Rota rows are always built via
    direct construction -- Rota(armazem_id=..., fabrica_id=..., ...) -- and
    never appended to a fabrica.rotas/armazem.rotas collection), so this is
    not a red-first bug-reproduction test.

    What actually deletes a Rota when its parent Fabrica/Armazem is deleted is
    the DB-level ForeignKey(..., ondelete='CASCADE') on Rota.fabrica_id /
    Rota.armazem_id, independent of the ORM-level cascade= on the
    relationships. This test locks in that real behavior as a safety net: it
    must PASS before the L4 fix (removing the redundant delete-orphan) and
    must STILL PASS after it, proving the fix didn't break the real
    cascade-delete behavior.
    """
    rota = Rota(
        cenario_id=cenario.id,
        armazem_id=armazem.id,
        fabrica_id=fabrica.id,
        distancia_km=50,
        custo_frete_ton=20.0,
        custo_frete_entressafra=15.0,
    )
    session.add(rota)
    session.commit()

    assert session.query(Rota).count() == 1

    session.delete(fabrica)
    session.commit()

    assert session.query(Rota).count() == 0
