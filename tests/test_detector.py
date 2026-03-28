def test_rule_based_jamming():
    from backend.config import settings
    from backend.ml.detector import AnomalyDetector
    det = AnomalyDetector(settings)
    features = [15.0, 10.0, 1.0, -5.0, 3, 5.0, 0.5, 0.1, 0.3, 0.1]
    typ, conf = det.rule_based(features)
    assert typ == 'JAMMING'
    assert conf > 0.8


def test_rule_based_spoofing():
    from backend.config import settings
    from backend.ml.detector import AnomalyDetector
    det = AnomalyDetector(settings)
    features = [44.0, 40.0, 0.7, 1.0, 11, 0.9, 450.0, 1.0, 8.0, 0.84]
    typ, conf = det.rule_based(features)
    assert typ == 'SPOOFING'
    assert conf > 0.8


def test_rule_based_nominal():
    from backend.config import settings
    from backend.ml.detector import AnomalyDetector
    det = AnomalyDetector(settings)
    features = [42.0, 36.0, 2.5, 0.1, 11, 0.85, 0.8, 0.1, 0.3, 0.82]
    typ, conf = det.rule_based(features)
    assert typ == 'NOMINAL'
