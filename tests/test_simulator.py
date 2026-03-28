def test_simulator_tick():
    from backend.config import settings
    from backend.gnss.simulator import GNSSSimulator
    sim = GNSSSimulator(settings)
    snap = sim.tick()
    assert snap.avg_cn0 > 0
    assert len(snap.satellites) == 24
    assert snap.receiver.visible_count >= 0


def test_jamming_reduces_cn0():
    from backend.config import settings
    from backend.gnss.simulator import GNSSSimulator
    sim = GNSSSimulator(settings)
    nominal = sim.tick().avg_cn0
    sim.set_attack('JAMMING', 1.0)
    jammed = sim.tick().avg_cn0
    assert jammed < nominal


def test_spoofing_increases_position_delta():
    from backend.config import settings
    from backend.gnss.simulator import GNSSSimulator
    sim = GNSSSimulator(settings)
    sim.set_attack('SPOOFING', 1.0, spoofing_subtype='POSITION_PUSH', spoofing_offset_m=500)
    snap = sim.tick()
    assert snap.receiver.position_error_m > 10
