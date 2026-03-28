"""
Attack Engine -- manages attack state transitions and ramp-up/ramp-down.
Decouples attack scheduling from the simulator.
"""
import time
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass
class AttackConfig:
    attack_type: str = "NOMINAL"
    intensity: float = 0.0
    jamming_subtype: str = "WIDEBAND"
    spoofing_subtype: str = "POSITION_PUSH"
    spoofing_offset_m: float = 500.0
    ramp_duration_s: float = 3.0


class AttackEngine:
    """
    Manages smooth intensity ramp-up/ramp-down for attacks.
    Can be controlled via API or run in auto-demo mode.
    """
    def __init__(self, simulator):
        self.sim = simulator
        self._config = AttackConfig()
        self._target_intensity = 0.0
        self._current_intensity = 0.0
        self._lock = threading.Lock()

        self.auto_demo = False
        self._demo_thread: Optional[threading.Thread] = None

    def start_attack(self, config: AttackConfig):
        with self._lock:
            self._config = config
            self._target_intensity = config.intensity
            self.sim.set_attack(
                config.attack_type,
                0.0,
                config.jamming_subtype,
                config.spoofing_subtype,
                config.spoofing_offset_m
            )

    def stop_attack(self):
        with self._lock:
            self._target_intensity = 0.0
            self._config.attack_type = "NOMINAL"

    def tick(self):
        """Call this every update cycle to ramp intensity."""
        with self._lock:
            dt = 1.0 / 2.0  # 2Hz update rate
            ramp_step = dt / max(0.1, self._config.ramp_duration_s)

            if self._current_intensity < self._target_intensity:
                self._current_intensity = min(
                    self._target_intensity,
                    self._current_intensity + ramp_step
                )
            elif self._current_intensity > self._target_intensity:
                self._current_intensity = max(
                    self._target_intensity,
                    self._current_intensity - ramp_step
                )

            attack_type = self._config.attack_type if self._current_intensity > 0.01 else "NOMINAL"
            self.sim.set_attack(
                attack_type,
                self._current_intensity,
                self._config.jamming_subtype,
                self._config.spoofing_subtype,
                self._config.spoofing_offset_m
            )

    def get_status(self) -> dict:
        with self._lock:
            return {
                "attack_type": self._config.attack_type,
                "target_intensity": self._target_intensity,
                "current_intensity": round(self._current_intensity, 3),
                "jamming_subtype": self._config.jamming_subtype,
                "spoofing_subtype": self._config.spoofing_subtype,
                "spoofing_offset_m": self._config.spoofing_offset_m,
                "is_active": self._current_intensity > 0.05,
            }

    def enable_auto_demo(self):
        """Automatically cycle through attacks for demo. Can be toggled."""
        self.auto_demo = True
        self._demo_thread = threading.Thread(target=self._demo_loop, daemon=True)
        self._demo_thread.start()

    def _demo_loop(self):
        """Demo cycle: 20s nominal -> 8s jamming -> 12s nominal -> 8s spoofing -> repeat."""
        while self.auto_demo:
            self.stop_attack()
            time.sleep(20)
            if not self.auto_demo:
                break

            self.start_attack(AttackConfig(attack_type="JAMMING", intensity=0.9, jamming_subtype="WIDEBAND"))
            time.sleep(8)
            if not self.auto_demo:
                break

            self.stop_attack()
            time.sleep(12)
            if not self.auto_demo:
                break

            self.start_attack(AttackConfig(attack_type="SPOOFING", intensity=0.85, spoofing_subtype="POSITION_PUSH"))
            time.sleep(8)
