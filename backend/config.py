from pydantic_settings import BaseSettings
from pathlib import Path
import os

BASE_DIR = Path(__file__).parent.parent

class Settings(BaseSettings):
    # App
    APP_NAME: str = "BKZS Anti-Spoofing System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # GNSS Simulation
    UPDATE_RATE_HZ: float = 2.0          # Samples per second
    NUM_SATELLITES: int = 24             # Total satellites to simulate
    NUM_BKZS_SATS: int = 6              # Primary BKZS satellites
    ANKARA_LAT: float = 39.93
    ANKARA_LON: float = 32.87

    # ML Model Paths
    MODEL_DIR: Path = BASE_DIR / "models"
    RF_MODEL_PATH: Path = MODEL_DIR / "random_forest.pkl"
    ISO_MODEL_PATH: Path = MODEL_DIR / "isolation_forest.pkl"
    SCALER_PATH: Path = MODEL_DIR / "scaler.pkl"

    # Data Paths
    DATA_RAW_DIR: Path = BASE_DIR / "data" / "raw"
    DATA_PROCESSED_DIR: Path = BASE_DIR / "data" / "processed"
    SAMPLE_DATA_PATH: Path = BASE_DIR / "data" / "sample" / "sample_gnss.csv"

    # Detection Thresholds (tunable)
    JAMMING_CN0_THRESHOLD: float = 24.0    # dB-Hz below this = jammed
    AGC_DROP_THRESHOLD: float = 0.35       # AGC level below this = jammed
    SPOOFING_DOPPLER_THRESHOLD: float = 6.0 # Doppler residual above = spoofed
    SPOOFING_POSITION_JUMP_M: float = 120.0 # Position jump > this = spoofed
    SPOOFING_CLOCK_JUMP_NS: float = 12.0    # Clock jump > this = spoofed

    # Alert History
    MAX_ALERT_HISTORY: int = 200

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

# Ensure model directory exists
settings.MODEL_DIR.mkdir(parents=True, exist_ok=True)
