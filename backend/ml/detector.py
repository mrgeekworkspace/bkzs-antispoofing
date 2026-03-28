"""
Real-time Anomaly Detector
Combines: Rule-based -> Random Forest -> Isolation Forest
Returns: detection type, confidence, method, scores
"""
import numpy as np
import joblib
from pathlib import Path
from typing import Optional
import logging

from .dataset_loader import FEATURE_COLS, LABEL_MAP_INV

logger = logging.getLogger(__name__)


class AnomalyDetector:
    def __init__(self, settings):
        self.settings = settings
        self.rf = None
        self.iso = None
        self.scaler = None
        self._loaded = False
        self._load_models()

    def _load_models(self):
        """Load models if they exist. Safe to call before training."""
        try:
            if (self.settings.RF_MODEL_PATH.exists() and
                self.settings.ISO_MODEL_PATH.exists() and
                self.settings.SCALER_PATH.exists()):
                self.rf = joblib.load(self.settings.RF_MODEL_PATH)
                self.iso = joblib.load(self.settings.ISO_MODEL_PATH)
                self.scaler = joblib.load(self.settings.SCALER_PATH)
                self._loaded = True
                logger.info("Anomaly detector: models loaded successfully")
            else:
                logger.warning("Anomaly detector: models not found -- rule-based only until training")
        except Exception as e:
            logger.error(f"Model load error: {e}")

    def reload(self):
        """Reload models after training."""
        self._load_models()

    @property
    def models_loaded(self) -> bool:
        return self._loaded

    def extract_features(self, snapshot) -> list:
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

    def rule_based(self, features: list) -> tuple:
        """
        Fast rule-based detection. First line of defense.
        Returns: (detection_type, confidence)
        """
        avg_cn0, min_cn0, std_cn0, cn0_delta, vis_count, hdop, pos_delta, clock_delta, doppler_res, agc = features
        s = self.settings

        # Jamming rules
        if avg_cn0 < s.JAMMING_CN0_THRESHOLD and agc < s.AGC_DROP_THRESHOLD:
            conf = min(0.98, 0.75 + (s.JAMMING_CN0_THRESHOLD - avg_cn0) * 0.01)
            return ('JAMMING', round(conf, 3))

        if vis_count < 4 and avg_cn0 < 28:
            return ('JAMMING', 0.82)

        if agc < 0.25:
            return ('JAMMING', 0.88)

        # Spoofing rules
        if pos_delta > s.SPOOFING_POSITION_JUMP_M and doppler_res > 4.0:
            conf = min(0.96, 0.75 + (pos_delta / 1000))
            return ('SPOOFING', round(conf, 3))

        if doppler_res > s.SPOOFING_DOPPLER_THRESHOLD and std_cn0 < 1.2:
            return ('SPOOFING', 0.88)

        if abs(clock_delta) > s.SPOOFING_CLOCK_JUMP_NS and pos_delta > 30:
            return ('SPOOFING', 0.84)

        return ('NOMINAL', 0.96)

    def detect(self, snapshot) -> dict:
        """
        Full detection pipeline: rule -> RF -> ISO.
        Returns a dict suitable for JSON serialization.
        """
        features = self.extract_features(snapshot)
        rule_type, rule_conf = self.rule_based(features)

        result = {
            "type": rule_type,
            "confidence": rule_conf,
            "method": "RULE",
            "rf_probs": {"NOMINAL": None, "JAMMING": None, "SPOOFING": None},
            "iso_score": None,
            "models_loaded": self._loaded,
            "features": dict(zip(FEATURE_COLS, [round(f, 3) for f in features])),
        }

        if not self._loaded:
            return result

        try:
            x = self.scaler.transform([features])

            # Random Forest
            rf_probs = self.rf.predict_proba(x)[0]
            rf_class_idx = int(np.argmax(rf_probs))
            rf_class = LABEL_MAP_INV[rf_class_idx]
            rf_conf = float(rf_probs[rf_class_idx])

            # Isolation Forest
            iso_score = float(-self.iso.score_samples(x)[0])
            is_anomaly = iso_score > 0.55

            result["rf_probs"] = {
                "NOMINAL": round(float(rf_probs[0]), 3),
                "JAMMING": round(float(rf_probs[1]), 3),
                "SPOOFING": round(float(rf_probs[2]), 3),
            }
            result["iso_score"] = round(iso_score, 3)

            # Decision fusion
            if rule_type != "NOMINAL" and rule_conf >= 0.85:
                pass  # rule-based wins for strong signals
            elif rf_conf >= 0.78:
                result["type"] = rf_class
                result["confidence"] = round(rf_conf, 3)
                result["method"] = "ML-RF"
            elif is_anomaly and rule_type == "NOMINAL":
                result["type"] = "ANOMALY"
                result["confidence"] = round(min(1.0, iso_score), 3)
                result["method"] = "ML-ISO"
            else:
                result["type"] = rf_class
                result["confidence"] = round(rf_conf, 3)
                result["method"] = "ML-RF"

        except Exception as e:
            logger.warning(f"ML inference error: {e}")

        return result
