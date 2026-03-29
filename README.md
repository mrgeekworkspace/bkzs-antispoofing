# BKZS Signal Validation & Anti-Spoofing System

Real-time GNSS signal validation and anti-spoofing prototype for BKZS (Bolgesel Konumlama ve Zamanlama Sistemi).

**TUA Astro Hackathon 2026**

## Features

- **GNSS Signal Simulator** — 24-satellite constellation (6 BKZS + 18 GPS) with realistic CN0, Doppler, AGC, clock bias
- **Attack Injection Engine** — Jamming (wideband/narrowband/pulsed) and spoofing (position push/time push/meaconing) with smooth intensity ramping
- **3-Layer ML Detection** — Rule-based + Random Forest (supervised) + Isolation Forest (unsupervised anomaly)
- **Real-Time Dashboard** — Interactive 3D globe with satellite tracking, connection lines, signal charts, anomaly scores
- **Red Team Control Panel** — Start/stop attacks with configurable parameters directly from the UI
- **WebSocket Streaming** — Live data at 2Hz for real-time visualization


![dashboard](image.png)

## Quick Start

### 1. Install

```bash
cd bkzs-antispoofing
python -m venv venv
source venv/bin/activate  # Linux/Mac
# OR: venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Download Dataset (Optional)

Download the Mendeley GNSS Dataset (Part III) and extract it into `data/raw/`:

**Dataset:** [GNSS Dataset with Interference and Spoofing — Part III](https://data.mendeley.com/datasets/nxk9r22wd6/3)

```
data/
  raw/
    GNSS Dataset (with Interference and Spoofing) Part III/
      1221/           # Attack data
      Processed data/ # Clean data (folders 21-30)
```

> If you skip this step, you can still train on simulated data — no download needed.

### 3. Train Models

```bash
# With simulated data (works immediately):
python scripts/train.py

# With Mendeley dataset:
python scripts/train.py --dataset mendeley --data-path data/raw/
```

You can also train directly from the dashboard UI (Model & Config section).

### 4. Run

```bash
python -m backend.main
```

Open: **http://localhost:8000**

## Dashboard

| Section | Description |
|---------|-------------|
| **Left Panel** | Live satellite list with per-satellite CN0, elevation |
| **Center** | Interactive 3D globe — satellites orbit, connection lines show signal quality |
| **Right Panel** | Anomaly scores (jamming/spoofing/integrity/isolation forest), signal history chart, detection log |
| **Bottom** | Red Team attack controls, model training, threshold tuning, alert feed |

### Injecting Attacks

From the Red Team Control Panel:

- **Jamming:** Select type (Wideband/Narrowband/Pulsed), set power and ramp duration
- **Spoofing:** Select type (Position Push/Time Push/Meaconing), set offset distance and ramp duration
- **Auto Demo:** Toggle for automatic attack cycling (20s nominal → 8s jam → 12s nominal → 8s spoof)

### REST API

```
GET  /api/status         System health and model status
GET  /api/snapshot       Single GNSS snapshot with detection
POST /api/attack/start   Start attack injection
POST /api/attack/stop    Stop all attacks
POST /api/train          Train ML models (background)
GET  /api/train/status   Training progress and results
POST /api/thresholds     Update detection thresholds
WS   /ws                 Live GNSS stream at 2Hz
```

## Architecture

```
GNSSSimulator ──► AttackEngine (intensity ramping)
       │
  GNSSSnapshot (10-dimensional feature vector)
       │
  AnomalyDetector:
    Layer 1: Rule-based    (instant, explainable)
    Layer 2: Random Forest (supervised, 3-class: NOMINAL/JAMMING/SPOOFING)
    Layer 3: Isolation Forest (unsupervised, catches novel attacks)
       │
  Decision Fusion ──► WebSocket broadcast ──► Dashboard UI
```

### Feature Vector

| Feature | Description |
|---------|-------------|
| avg_cn0 | Mean C/N0 across visible satellites |
| min_cn0 | Minimum C/N0 |
| std_cn0 | CN0 standard deviation |
| cn0_delta | CN0 change rate |
| visible_count | Number of visible satellites |
| hdop | Horizontal dilution of precision |
| pos_delta_m | Position jump in meters |
| clock_offset_delta_ns | Clock bias change rate |
| doppler_residual | Doppler consistency metric |
| agc_level | Automatic gain control level |

## Project Structure

```
bkzs-antispoofing/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Settings and thresholds
│   ├── gnss/
│   │   ├── simulator.py     # GNSS signal simulator
│   │   └── attack_engine.py # Attack injection with ramping
│   ├── ml/
│   │   ├── detector.py      # 3-layer anomaly detection
│   │   ├── trainer.py       # Model training pipeline
│   │   └── dataset_loader.py # Mendeley + synthetic data
│   └── api/
│       ├── routes.py        # REST endpoints
│       └── websocket.py     # WebSocket streaming
├── frontend/
│   ├── index.html           # Dashboard layout
│   ├── css/dashboard.css    # Styling
│   └── js/
│       ├── dashboard.js     # Main controller
│       └── globe.js         # 3D globe (Three.js)
├── scripts/
│   ├── train.py             # CLI training script
│   └── prepare_dataset.py   # Dataset preparation
├── tests/                   # Unit tests
├── data/                    # Dataset directory (download separately)
├── models/                  # Trained model files
└── requirements.txt
```

## Dataset

**Source:** [Yunnan University — GNSS Dataset with Interference and Spoofing (Part III)](https://data.mendeley.com/datasets/nxk9r22wd6/3)

This dataset contains real GNSS observations with interference and spoofing scenarios. Place the extracted data in `data/raw/`. The system also supports training on fully synthetic data if the dataset is not available.

## License

MIT
