# BKZS Anti-Spoofing API Reference

## REST Endpoints

### GET /api/status
System health and current state.

### GET /api/snapshot
Single GNSS snapshot with detection result.

### POST /api/attack/start
Inject an attack.
```json
{
  "attack_type": "JAMMING",
  "intensity": 0.8,
  "jamming_subtype": "WIDEBAND",
  "spoofing_subtype": "POSITION_PUSH",
  "spoofing_offset_m": 500,
  "ramp_duration_s": 3.0
}
```

### POST /api/attack/stop
Stop any active attack.

### GET /api/attack/status
Current attack state.

### POST /api/attack/auto-demo?enable=true
Toggle automatic attack cycle.

### POST /api/thresholds
Update detection thresholds.
```json
{
  "jamming_cn0_threshold": 24.0,
  "agc_drop_threshold": 0.35,
  "spoofing_doppler_threshold": 6.0,
  "spoofing_position_jump_m": 120.0,
  "spoofing_clock_jump_ns": 12.0
}
```

### POST /api/train
Trigger model training.
```json
{
  "dataset_type": "simulate",
  "n_estimators": 150,
  "data_path": null
}
```

### GET /api/train/status
Training progress and results.

## WebSocket

### WS /ws
Live GNSS data stream at 2Hz. Each message:
```json
{
  "type": "gnss_update",
  "ts": 1234567890.123,
  "receiver": { "lat": 39.93, "lon": 32.87, ... },
  "features": { "avg_cn0": 42.1, ... },
  "satellites": [ { "prn": "BKZS-01", ... } ],
  "detection": { "type": "NOMINAL", "confidence": 0.96, "method": "ML-RF", ... },
  "attack_state": { "attack_type": "NOMINAL", "is_active": false, ... }
}
```
