"""
WebSocket handler -- streams live GNSS data at 2Hz.
Client receives JSON messages every 500ms.
"""
import asyncio
import json
import time
from fastapi import WebSocket, WebSocketDisconnect
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WS client connected. Total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        logger.info(f"WS client disconnected. Total: {len(self.active)}")

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self.active:
                self.active.remove(ws)


manager = ConnectionManager()


def create_ws_handler(simulator, attack_engine, detector):

    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                loop_start = time.time()

                attack_engine.tick()
                snap = simulator.tick()
                detection = detector.detect(snap)

                message = {
                    "type": "gnss_update",
                    "ts": round(snap.timestamp, 3),
                    "receiver": {
                        "lat": round(snap.receiver.lat, 7),
                        "lon": round(snap.receiver.lon, 7),
                        "hdop": snap.receiver.hdop,
                        "pdop": snap.receiver.pdop,
                        "fix_type": snap.receiver.fix_type,
                        "clock_bias_ns": snap.receiver.clock_bias_ns,
                        "agc_level": snap.receiver.agc_level,
                        "visible_count": snap.receiver.visible_count,
                        "position_error_m": snap.receiver.position_error_m,
                    },
                    "features": {
                        "avg_cn0": snap.avg_cn0,
                        "min_cn0": snap.min_cn0,
                        "std_cn0": snap.std_cn0,
                        "cn0_delta": snap.cn0_delta,
                        "doppler_residual": snap.doppler_residual,
                        "pos_delta_m": snap.pos_delta_m,
                        "clock_offset_delta_ns": snap.clock_offset_delta_ns,
                    },
                    "satellites": [
                        {
                            "prn": s.prn, "is_bkzs": s.is_bkzs,
                            "cn0": round(s.cn0, 1), "elevation": round(s.elevation, 1),
                            "visible": s.visible, "doppler": round(s.doppler, 2),
                        }
                        for s in snap.satellites
                    ],
                    "detection": detection,
                    "attack_state": attack_engine.get_status(),
                }

                await manager.broadcast(message)

                elapsed = time.time() - loop_start
                sleep_time = max(0, 0.5 - elapsed)
                await asyncio.sleep(sleep_time)

        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception as e:
            logger.error(f"WS error: {e}")
            manager.disconnect(websocket)

    return websocket_endpoint
