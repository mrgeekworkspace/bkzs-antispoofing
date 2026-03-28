"""
REST API endpoints for BKZS Anti-Spoofing System.
All endpoints return JSON. WebSocket is in websocket.py.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["BKZS API"])


class AttackRequest(BaseModel):
    attack_type: str = Field(..., description="NOMINAL | JAMMING | SPOOFING")
    intensity: float = Field(0.8, ge=0.0, le=1.0)
    jamming_subtype: str = Field("WIDEBAND")
    spoofing_subtype: str = Field("POSITION_PUSH")
    spoofing_offset_m: float = Field(500.0, ge=0, le=5000)
    ramp_duration_s: float = Field(3.0, ge=0.5, le=30.0)


class ThresholdUpdateRequest(BaseModel):
    jamming_cn0_threshold: Optional[float] = None
    agc_drop_threshold: Optional[float] = None
    spoofing_doppler_threshold: Optional[float] = None
    spoofing_position_jump_m: Optional[float] = None
    spoofing_clock_jump_ns: Optional[float] = None


class TrainRequest(BaseModel):
    dataset_type: str = Field("simulate")
    n_estimators: int = Field(150, ge=10, le=1000)
    data_path: Optional[str] = None


def create_routes(simulator, attack_engine, detector, settings):

    @router.get("/status")
    def get_status():
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "models_loaded": detector.models_loaded,
            "attack": attack_engine.get_status(),
            "auto_demo": attack_engine.auto_demo,
        }

    @router.get("/snapshot")
    def get_snapshot():
        attack_engine.tick()
        snap = simulator.tick()
        detection = detector.detect(snap)
        return {
            "timestamp": snap.timestamp,
            "receiver": {
                "lat": snap.receiver.lat, "lon": snap.receiver.lon,
                "alt": snap.receiver.alt, "hdop": snap.receiver.hdop,
                "pdop": snap.receiver.pdop, "fix_type": snap.receiver.fix_type,
                "clock_bias_ns": snap.receiver.clock_bias_ns,
                "agc_level": snap.receiver.agc_level,
                "visible_count": snap.receiver.visible_count,
                "position_error_m": snap.receiver.position_error_m,
            },
            "features": {
                "avg_cn0": snap.avg_cn0, "min_cn0": snap.min_cn0,
                "std_cn0": snap.std_cn0, "cn0_delta": snap.cn0_delta,
                "doppler_residual": snap.doppler_residual,
            },
            "satellites": [
                {"prn": s.prn, "is_bkzs": s.is_bkzs, "cn0": round(s.cn0, 1),
                 "elevation": round(s.elevation, 1), "visible": s.visible}
                for s in snap.satellites
            ],
            "detection": detection,
        }

    @router.post("/attack/start")
    def start_attack(req: AttackRequest):
        from ..gnss.attack_engine import AttackConfig
        config = AttackConfig(
            attack_type=req.attack_type,
            intensity=req.intensity,
            jamming_subtype=req.jamming_subtype,
            spoofing_subtype=req.spoofing_subtype,
            spoofing_offset_m=req.spoofing_offset_m,
            ramp_duration_s=req.ramp_duration_s,
        )
        attack_engine.start_attack(config)
        return {"status": "ok", "attack": attack_engine.get_status()}

    @router.post("/attack/stop")
    def stop_attack():
        attack_engine.stop_attack()
        return {"status": "ok", "attack": attack_engine.get_status()}

    @router.get("/attack/status")
    def attack_status():
        return attack_engine.get_status()

    @router.post("/attack/auto-demo")
    def toggle_auto_demo(enable: bool = True):
        if enable:
            attack_engine.enable_auto_demo()
        else:
            attack_engine.auto_demo = False
        return {"auto_demo": enable}

    @router.post("/thresholds")
    def update_thresholds(req: ThresholdUpdateRequest):
        if req.jamming_cn0_threshold is not None:
            settings.JAMMING_CN0_THRESHOLD = req.jamming_cn0_threshold
        if req.agc_drop_threshold is not None:
            settings.AGC_DROP_THRESHOLD = req.agc_drop_threshold
        if req.spoofing_doppler_threshold is not None:
            settings.SPOOFING_DOPPLER_THRESHOLD = req.spoofing_doppler_threshold
        if req.spoofing_position_jump_m is not None:
            settings.SPOOFING_POSITION_JUMP_M = req.spoofing_position_jump_m
        if req.spoofing_clock_jump_ns is not None:
            settings.SPOOFING_CLOCK_JUMP_NS = req.spoofing_clock_jump_ns
        return {"status": "ok", "settings": {
            "jamming_cn0_threshold": settings.JAMMING_CN0_THRESHOLD,
            "agc_drop_threshold": settings.AGC_DROP_THRESHOLD,
            "spoofing_doppler_threshold": settings.SPOOFING_DOPPLER_THRESHOLD,
            "spoofing_position_jump_m": settings.SPOOFING_POSITION_JUMP_M,
            "spoofing_clock_jump_ns": settings.SPOOFING_CLOCK_JUMP_NS,
        }}

    @router.post("/train")
    async def train_model(req: TrainRequest, background_tasks: BackgroundTasks):
        from ..ml.trainer import train as run_training

        training_state["running"] = True
        training_state["result"] = None
        training_state["error"] = None

        async def _train():
            from pathlib import Path
            try:
                data_dir = Path(req.data_path) if req.data_path else settings.DATA_RAW_DIR
                result = run_training(
                    settings,
                    data_dir=data_dir,
                    dataset_type=req.dataset_type,
                    n_estimators_rf=req.n_estimators
                )
                training_state["result"] = result
                detector.reload()
            except Exception as e:
                training_state["error"] = str(e)
            finally:
                training_state["running"] = False

        background_tasks.add_task(_train)
        return {"status": "training_started", "poll": "/api/train/status"}

    @router.get("/train/status")
    def train_status():
        return {
            "running": training_state["running"],
            "result": training_state["result"],
            "error": training_state["error"],
            "models_loaded": detector.models_loaded,
        }

    training_state = {"running": False, "result": None, "error": None}
    return router
