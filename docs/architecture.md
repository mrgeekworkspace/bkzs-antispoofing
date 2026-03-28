# BKZS Anti-Spoofing System — Architecture

## Overview

```
GNSSSimulator --> AttackEngine (ramp control)
     |
GNSSSnapshot (10-dim feature vector)
     |
AnomalyDetector:
  1. Rule-based (instant, explainable)
  2. Random Forest (supervised, 3-class)
  3. Isolation Forest (unsupervised, catches novel attacks)
     |
FastAPI --> WebSocket broadcast --> Dashboard UI
```

## Components

### GNSS Simulator (`backend/gnss/simulator.py`)
- Simulates 24-satellite constellation (6 BKZS + 18 GPS)
- Generates realistic CN0, Doppler, AGC, position, and clock data
- Supports attack injection: jamming (wideband/narrowband/pulsed) and spoofing (position push/time push/meaconing)

### Attack Engine (`backend/gnss/attack_engine.py`)
- Manages smooth intensity ramp-up/ramp-down
- Auto-demo mode cycles through attack types
- Thread-safe, controlled via REST API

### ML Pipeline (`backend/ml/`)
- **Dataset Loader**: Supports Mendeley Part III JSON + synthetic generation
- **Trainer**: Random Forest (150 trees) + Isolation Forest (200 trees)
- **Detector**: 3-layer fusion: Rule -> RF -> Isolation Forest

### API (`backend/api/`)
- REST endpoints for control and status
- WebSocket at `/ws` streams at 2Hz

### Frontend (`frontend/`)
- Three.js 3D globe with satellite orbits
- Real-time signal chart, satellite list, anomaly scores
- Red team attack control panel
