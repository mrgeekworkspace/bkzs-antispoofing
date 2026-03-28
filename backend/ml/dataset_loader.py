"""
Dataset Loader -- supports:
  1. Yunnan University / Mendeley dataset (Part III JSON format)
  2. Simulation-generated data
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
import json
import logging

logger = logging.getLogger(__name__)

FEATURE_COLS = [
    'avg_cn0', 'min_cn0', 'std_cn0', 'cn0_delta',
    'visible_count', 'hdop', 'pos_delta_m',
    'clock_offset_delta_ns', 'doppler_residual', 'agc_level'
]

LABEL_COL = 'label'
LABEL_MAP = {'NOMINAL': 0, 'JAMMING': 1, 'SPOOFING': 2}
LABEL_MAP_INV = {v: k for k, v in LABEL_MAP.items()}


def load_mendeley(data_dir: Path) -> pd.DataFrame:
    """
    Load Yunnan University Mendeley Part III dataset.
    Expected structure: data_dir contains folders like 1221/ with Processed data/ inside,
    each containing observation*.json, pvtSolution*.json, satelliteInfomation*.json files.
    """
    logger.info(f"Loading Mendeley dataset from {data_dir}")
    rows = []

    # Find the root dataset folder (may be nested)
    candidates = list(data_dir.rglob("observation*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"Could not find observation*.json files in {data_dir}. "
            "Expected Mendeley Part III JSON files."
        )

    # Group files by parent directory
    parent_dirs = set(f.parent for f in candidates)
    logger.info(f"Found observation files in {len(parent_dirs)} directories")

    for parent in sorted(parent_dirs):
        obs_files = sorted(parent.glob("observation*.json"))
        pvt_files = sorted(parent.glob("pvtSolution*.json"))
        sat_files = sorted(parent.glob("satelliteInfomation*.json"))

        # Determine label from path: 1221 folder = attack data
        path_str = str(parent)
        is_attack_folder = '1221' in path_str

        for obs_file in obs_files:
            try:
                # Extract hour number from filename (e.g., observation12.json -> 12)
                hour_str = obs_file.stem.replace('observation', '')
                pvt_file = parent / f"pvtSolution{hour_str}.json"
                sat_file = parent / f"satelliteInfomation{hour_str}.json"

                batch_rows = _parse_json_epoch(obs_file, pvt_file, sat_file,
                                               is_attack_folder, int(hour_str))
                rows.extend(batch_rows)
            except Exception as e:
                logger.debug(f"Skip {obs_file}: {e}")
                continue

    if not rows:
        raise ValueError("Could not parse any rows from the dataset.")

    df = pd.DataFrame(rows)

    # Compute rolling deltas
    df['cn0_delta'] = df['avg_cn0'].diff().fillna(0)
    df['clock_offset_delta_ns'] = df.get('_clock_ns', pd.Series(dtype=float)).diff().fillna(0)
    df = df.drop(columns=['_clock_ns'], errors='ignore')

    logger.info(f"Loaded {len(df)} samples. Label distribution:\n{df['label'].value_counts()}")
    return df[FEATURE_COLS + [LABEL_COL]]


def _parse_json_epoch(obs_file: Path, pvt_file: Path, sat_file: Path,
                      is_attack: bool, hour: int) -> list:
    """Parse epochs from Mendeley Part III JSON files."""
    with open(obs_file, 'r') as f:
        obs = json.load(f)

    # cn0 keys: cn0_G1, cn0_G2, cn0_E1, cn0_E2, cn0_B1, cn0_B2, etc.
    cn0_keys = [k for k in obs.keys() if k.startswith('cn0_')]
    if not cn0_keys:
        return []

    n_epochs = len(obs[cn0_keys[0]])

    # Load PVT if available
    pvt = {}
    if pvt_file.exists():
        with open(pvt_file, 'r') as f:
            pvt = json.load(f)

    # Load satellite info if available
    sat_info = {}
    if sat_file.exists():
        with open(sat_file, 'r') as f:
            sat_info = json.load(f)

    hdop_list = pvt.get('hDOP', [])
    lat_list = pvt.get('lat', [])
    lon_list = pvt.get('lon', [])
    clk_list = pvt.get('clkB', [])
    num_sv_list = sat_info.get('numSvs', [])

    rows = []
    prev_lat, prev_lon = None, None

    # Sample every 10th epoch for speed (3600 -> 360 per file)
    step = max(1, n_epochs // 360)
    for i in range(0, n_epochs, step):
        # Gather all CN0 values for this epoch across all constellations
        all_cn0 = []
        for key in cn0_keys:
            epoch_cn0 = obs[key][i] if i < len(obs[key]) else []
            if isinstance(epoch_cn0, list):
                nonzero = [v for v in epoch_cn0 if v > 0]
                all_cn0.extend(nonzero)

        if len(all_cn0) < 3:
            continue

        avg_cn0 = float(np.mean(all_cn0))
        min_cn0 = float(np.min(all_cn0))
        std_cn0 = float(np.std(all_cn0))

        visible_count = len(all_cn0)
        hdop = float(hdop_list[i]) if i < len(hdop_list) else 1.0
        lat = float(lat_list[i]) if i < len(lat_list) else 0.0
        lon = float(lon_list[i]) if i < len(lon_list) else 0.0
        clk = float(clk_list[i]) if i < len(clk_list) else 0.0

        # Position delta
        if prev_lat is not None and lat != 0:
            pos_delta = _haversine(prev_lat, prev_lon, lat, lon)
        else:
            pos_delta = 0.0
        prev_lat, prev_lon = lat, lon

        # Doppler residual: estimate from pseudorange rate variance
        doppler_res = std_cn0 * 0.15  # heuristic proxy

        # AGC estimate: normalized from CN0 pattern
        agc = min(1.0, avg_cn0 / 50.0)

        # Label assignment
        if is_attack:
            if avg_cn0 < 25:
                label = 'JAMMING'
            elif std_cn0 < 1.5 and avg_cn0 > 40:
                label = 'SPOOFING'
            else:
                label = 'SPOOFING'  # attack folder default
        else:
            label = 'NOMINAL'

        rows.append({
            'avg_cn0': avg_cn0,
            'min_cn0': min_cn0,
            'std_cn0': std_cn0,
            'cn0_delta': 0.0,
            'visible_count': visible_count,
            'hdop': hdop,
            'pos_delta_m': pos_delta,
            'clock_offset_delta_ns': 0.0,
            'doppler_residual': doppler_res,
            'agc_level': agc,
            '_clock_ns': clk,
            'label': label,
        })

    return rows


def _haversine(lat1, lon1, lat2, lon2) -> float:
    """Distance in meters between two lat/lon points."""
    import math
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.asin(math.sqrt(max(0, min(1, a))))


def generate_synthetic_dataset(n_per_class: int = 5000) -> pd.DataFrame:
    """
    Generate a synthetic labeled dataset.
    Used when no real dataset is available, or to augment a real dataset.
    """
    np.random.seed(42)
    rows, labels = [], []

    def nominal():
        return [
            42 + np.random.normal(0, 2),
            36 + np.random.normal(0, 1.5),
            2.5 + np.random.normal(0, 0.5),
            np.random.normal(0, 0.3),
            int(np.random.uniform(9, 13)),
            0.85 + np.random.normal(0, 0.1),
            0.8 + abs(np.random.normal(0, 0.4)),
            np.random.normal(0, 0.5),
            0.3 + abs(np.random.normal(0, 0.1)),
            0.82 + np.random.normal(0, 0.03),
        ]

    def jamming(subtype="WIDEBAND"):
        i = np.random.uniform(0.3, 1.0)
        cn0_drop = 24 if subtype == "WIDEBAND" else (14 if subtype == "NARROWBAND" else 18)
        return [
            42 - i*cn0_drop + np.random.normal(0, 2),
            36 - i*(cn0_drop+2) + np.random.normal(0, 2),
            1.5 + np.random.normal(0, 0.5),
            -i*5 + np.random.normal(0, 1),
            max(0, int(12 - i*10)),
            2.5 + i*4 + np.random.normal(0, 0.3),
            np.random.normal(0, 0.3),
            np.random.normal(0, 0.3),
            0.4 + np.random.normal(0, 0.1),
            0.82 - i*0.68 + np.random.normal(0, 0.02),
        ]

    def spoofing(subtype="POSITION_PUSH"):
        i = np.random.uniform(0.3, 1.0)
        pos_jump = 380 if subtype == "POSITION_PUSH" else (25 if subtype == "TIME_PUSH" else 60)
        clock_jump = 18 if subtype == "TIME_PUSH" else (2.5 if subtype == "POSITION_PUSH" else 5)
        return [
            44 + i*3 + np.random.normal(0, 1.5),
            40 + i*2 + np.random.normal(0, 1),
            0.8 + np.random.normal(0, 0.2),
            i*2 + np.random.normal(0, 0.5),
            int(np.random.uniform(9, 13)),
            0.90 + np.random.normal(0, 0.08),
            i * pos_jump + np.random.normal(0, 20),
            i * clock_jump + np.random.normal(0, 1),
            i * 12 + np.random.normal(0, 1.5),
            0.84 + np.random.normal(0, 0.02),
        ]

    for _ in range(n_per_class):
        rows.append(nominal());    labels.append('NOMINAL')
        rows.append(jamming());    labels.append('JAMMING')
        rows.append(jamming("NARROWBAND")); labels.append('JAMMING')
        rows.append(jamming("PULSED")); labels.append('JAMMING')
        rows.append(spoofing()); labels.append('SPOOFING')
        rows.append(spoofing("TIME_PUSH")); labels.append('SPOOFING')
        rows.append(spoofing("MEACONING")); labels.append('SPOOFING')

    df = pd.DataFrame(rows, columns=FEATURE_COLS)
    df[LABEL_COL] = labels
    return df


def load_or_generate(data_dir: Path, dataset_type: str = "simulate") -> pd.DataFrame:
    """
    Main entry point. Returns a labeled DataFrame ready for training.
    dataset_type: "mendeley" | "jammertest" | "simulate"
    """
    if dataset_type == "mendeley" and data_dir.exists():
        try:
            df = load_mendeley(data_dir)
            # Check class balance — augment underrepresented classes
            label_counts = df[LABEL_COL].value_counts()
            min_class_count = label_counts.min()
            if min_class_count < 500:
                logger.warning(f"Class imbalance detected (min={min_class_count}). Augmenting with synthetic data.")
                synthetic = generate_synthetic_dataset(n_per_class=2000)
                df = pd.concat([df, synthetic], ignore_index=True)
                logger.info(f"After augmentation: {len(df)} samples. {df[LABEL_COL].value_counts().to_dict()}")
            return df
        except Exception as e:
            logger.warning(f"Could not load Mendeley dataset: {e}. Falling back to simulation.")

    logger.info("Generating synthetic dataset (5000 samples per class x 3 subtypes)")
    return generate_synthetic_dataset(n_per_class=5000)
