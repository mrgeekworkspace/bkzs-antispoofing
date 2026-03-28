"""
FastAPI Application Entry Point
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from .config import settings
from .gnss.simulator import GNSSSimulator
from .gnss.attack_engine import AttackEngine
from .ml.detector import AnomalyDetector
from .api.routes import create_routes
from .api.websocket import create_ws_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

simulator = GNSSSimulator(settings)
attack_engine = AttackEngine(simulator)
detector = AnomalyDetector(settings)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


async def _attack_ticker(engine):
    """Background task that ticks the attack engine at 2Hz regardless of WS clients."""
    import asyncio
    while True:
        engine.tick()
        await asyncio.sleep(0.5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Models loaded: {detector.models_loaded}")
    if not detector.models_loaded:
        logger.warning("No trained models found. Run training from the dashboard or: python scripts/train.py")
    task = asyncio.create_task(_attack_ticker(attack_engine))
    yield
    task.cancel()
    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = create_routes(simulator, attack_engine, detector, settings)
app.include_router(api_router)

ws_handler = create_ws_handler(simulator, attack_engine, detector)
app.add_api_websocket_route("/ws", ws_handler)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{path:path}")
    def serve_frontend(path: str):
        file_path = FRONTEND_DIR / path
        if file_path.exists():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
