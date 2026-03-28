"""
Feature Extractor -- Extract ML features from raw GNSS data.
"""
import numpy as np
from typing import List


FEATURE_NAMES = [
    'avg_cn0', 'min_cn0', 'std_cn0', 'cn0_delta',
    'visible_count', 'hdop', 'pos_delta_m',
    'clock_offset_delta_ns', 'doppler_residual', 'agc_level'
]


def extract_features_from_snapshot(snapshot) -> list:
    """Extract 10-dim feature vector from a GNSSSnapshot."""
    return [
        snapshot.avg_cn0,
        snapshot.min_cn0,
        snapshot.std_cn0,
        snapshot.cn0_delta,
        snapshot.visible_count,
        snapshot.hdop,
        snapshot.pos_delta_m,
        snapshot.clock_offset_delta_ns,
        snapshot.doppler_residual,
        snapshot.agc_level,
    ]
