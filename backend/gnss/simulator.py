"""
GNSS Signal Simulator
Generates realistic receiver telemetry for BKZS constellation.
Supports normal operation, jamming attacks, and spoofing attacks.
"""
import numpy as np
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class SatelliteState:
    prn: str
    is_bkzs: bool
    orbital_plane: int
    phase0: float
    speed: float          # rad/ms
    cn0_base: float       # nominal C/N0 in dB-Hz
    cn0: float = 0.0
    elevation: float = 0.0
    azimuth: float = 0.0
    doppler: float = 0.0
    pseudorange: float = 0.0
    visible: bool = True


@dataclass
class ReceiverState:
    lat: float = 39.93
    lon: float = 32.87
    alt: float = 890.0
    hdop: float = 0.85
    pdop: float = 1.24
    fix_type: int = 3         # 3 = 3D fix
    clock_bias_ns: float = 2.3
    agc_level: float = 0.83
    visible_count: int = 11
    position_error_m: float = 1.4


@dataclass
class GNSSSnapshot:
    """One complete snapshot of receiver state -- fed to ML detector."""
    timestamp: float
    satellites: List[SatelliteState]
    receiver: ReceiverState

    # Derived features (computed by feature_extractor)
    avg_cn0: float = 0.0
    min_cn0: float = 0.0
    std_cn0: float = 0.0
    cn0_delta: float = 0.0
    visible_count: int = 0
    hdop: float = 0.0
    pos_delta_m: float = 0.0
    clock_offset_delta_ns: float = 0.0
    doppler_residual: float = 0.0
    agc_level: float = 0.0

    # Ground truth (for training / evaluation)
    true_label: Optional[str] = None   # NOMINAL / JAMMING / SPOOFING


class GNSSSimulator:
    """
    Simulates a GNSS receiver in Ankara, Turkey.
    Supports live attack injection with configurable intensity.
    """

    NUM_PLANES = 6
    SATS_PER_PLANE = 4
    ORBITAL_RADIUS = 2.55   # scaled, dimensionless
    EARTH_RADIUS = 1.5      # scaled
    INCLINATION = math.radians(55)

    def __init__(self, settings):
        self.settings = settings
        self._satellites: List[SatelliteState] = []
        self._start_time = time.time() * 1000  # ms

        # Attack state (controlled externally via API)
        self.attack_type: str = "NOMINAL"   # NOMINAL / JAMMING / SPOOFING
        self.attack_intensity: float = 0.0  # 0.0 - 1.0
        self.jamming_subtype: str = "WIDEBAND"  # WIDEBAND / NARROWBAND / PULSED
        self.spoofing_subtype: str = "POSITION_PUSH"  # POSITION_PUSH / TIME_PUSH / MEACONING
        self.spoofing_offset_m: float = 500.0  # position push distance in meters

        # Previous snapshot (for delta computation)
        self._prev_avg_cn0: float = 42.0
        self._prev_lat: float = settings.ANKARA_LAT
        self._prev_lon: float = settings.ANKARA_LON
        self._prev_clock_ns: float = 2.3

        self._init_satellites()

    def _init_satellites(self):
        """Create 24-satellite constellation (6 planes x 4 sats, 6 are BKZS primary)."""
        idx = 0
        for p in range(self.NUM_PLANES):
            for s in range(self.SATS_PER_PLANE):
                is_bkzs = (p < 2 and s < 3)
                prn = f"BKZS-{p*3+s+1:02d}" if is_bkzs else f"GPS-{idx+1:02d}"
                self._satellites.append(SatelliteState(
                    prn=prn,
                    is_bkzs=is_bkzs,
                    orbital_plane=p,
                    phase0=(s / self.SATS_PER_PLANE) * 2 * math.pi + p * 0.53,
                    speed=5.8e-5 + np.random.uniform(0, 1.4e-5),
                    cn0_base=37.0 + np.random.uniform(0, 9.0),
                ))
                idx += 1

    def set_attack(self, attack_type: str, intensity: float,
                   jamming_subtype: str = "WIDEBAND",
                   spoofing_subtype: str = "POSITION_PUSH",
                   spoofing_offset_m: float = 500.0):
        """Called by API to inject an attack. Thread-safe assignment."""
        self.attack_type = attack_type.upper()
        self.attack_intensity = max(0.0, min(1.0, intensity))
        self.jamming_subtype = jamming_subtype
        self.spoofing_subtype = spoofing_subtype
        self.spoofing_offset_m = spoofing_offset_m

    def _compute_cn0(self, sat: SatelliteState, t_ms: float) -> float:
        """Compute C/N0 with noise + attack degradation."""
        base = sat.cn0_base + math.sin(t_ms * 0.0011 + sat.phase0) * 1.3
        noise = np.random.normal(0, 0.4)

        if self.attack_type == "JAMMING":
            i = self.attack_intensity
            if self.jamming_subtype == "PULSED":
                pulse = 1.0 if math.sin(t_ms * 0.012) > 0 else 0.0
                base -= i * 24 * pulse
            elif self.jamming_subtype == "NARROWBAND":
                if sat.is_bkzs:
                    base -= i * 20
                else:
                    base -= i * 8
            else:  # WIDEBAND
                base -= i * 23

        elif self.attack_type == "SPOOFING":
            if self.spoofing_subtype == "MEACONING":
                base += self.attack_intensity * 2.0
            else:
                base += self.attack_intensity * 3.5

        return base + noise

    def _compute_doppler_residual(self, t_ms: float) -> float:
        """Doppler residual vs orbital model. High under spoofing."""
        if self.attack_type == "SPOOFING":
            return self.attack_intensity * 12.0 + np.random.normal(0, 1.5)
        return abs(np.random.normal(0, 0.35))

    def _compute_position(self) -> tuple:
        """Return (lat, lon, error_m) -- position jumps under spoofing."""
        base_lat = self.settings.ANKARA_LAT + np.random.normal(0, 0.00001)
        base_lon = self.settings.ANKARA_LON + np.random.normal(0, 0.00001)

        if self.attack_type == "SPOOFING":
            i = self.attack_intensity
            if self.spoofing_subtype == "POSITION_PUSH":
                lat_off = i * (self.spoofing_offset_m / 111320)
                base_lat += lat_off
                error_m = i * self.spoofing_offset_m * 1.05
            elif self.spoofing_subtype == "TIME_PUSH":
                base_lat += i * 0.0002
                error_m = i * 25.0
            else:  # MEACONING
                base_lat += i * 0.0005
                base_lon += i * 0.0005
                error_m = i * 60.0
        else:
            error_m = 0.8 + abs(np.random.normal(0, 0.6))

        return base_lat, base_lon, error_m

    def _compute_clock_bias(self, t_ms: float) -> float:
        """Clock bias in nanoseconds. Jumps under spoofing/time-push."""
        base = 2.3 + math.sin(t_ms * 0.00005) * 0.8

        if self.attack_type == "SPOOFING":
            if self.spoofing_subtype == "TIME_PUSH":
                base += self.attack_intensity * 250.0
            else:
                base += self.attack_intensity * 18.0

        return base + np.random.normal(0, 0.3)

    def _compute_agc(self) -> float:
        """AGC drops sharply under wideband jamming."""
        base = 0.83 + np.random.normal(0, 0.02)
        if self.attack_type == "JAMMING":
            if self.jamming_subtype == "WIDEBAND":
                base -= self.attack_intensity * 0.68
            elif self.jamming_subtype == "PULSED":
                pulse = 1.0 if math.sin(time.time() * 2 * math.pi) > 0 else 0.5
                base -= self.attack_intensity * 0.5 * pulse
            else:
                base -= self.attack_intensity * 0.3
        return max(0.05, min(1.0, base))

    def tick(self) -> GNSSSnapshot:
        """Advance simulation by one step. Returns a full snapshot."""
        t_ms = time.time() * 1000 - self._start_time

        # Update each satellite
        for sat in self._satellites:
            sat.cn0 = self._compute_cn0(sat, t_ms)
            sat.elevation = max(0, 15 + 40 * math.sin(sat.phase0 + t_ms * sat.speed * 0.1))
            sat.visible = sat.elevation > 5.0
            sat.doppler = np.random.normal(0, 0.3) + (
                self.attack_intensity * 8 if self.attack_type == "SPOOFING" else 0
            )

        visible_sats = [s for s in self._satellites if s.visible]
        cn0_vals = [s.cn0 for s in visible_sats] if visible_sats else [0]

        avg_cn0 = float(np.mean(cn0_vals))
        min_cn0 = float(np.min(cn0_vals))
        std_cn0 = float(np.std(cn0_vals))

        lat, lon, pos_err = self._compute_position()
        clock_ns = self._compute_clock_bias(t_ms)
        agc = self._compute_agc()

        hdop_base = 0.85 + np.random.normal(0, 0.08)
        if self.attack_type == "JAMMING":
            hdop_base += self.attack_intensity * 4.5

        visible_count = len(visible_sats)
        if self.attack_type == "JAMMING" and self.attack_intensity > 0.7:
            fix_type = 0
        elif self.attack_type == "JAMMING" and self.attack_intensity > 0.4:
            fix_type = 2
        else:
            fix_type = 3

        pos_delta = self._haversine(self._prev_lat, self._prev_lon, lat, lon)
        clock_delta = clock_ns - self._prev_clock_ns

        receiver = ReceiverState(
            lat=lat, lon=lon, alt=890.0 + np.random.normal(0, 0.5),
            hdop=round(hdop_base, 3),
            pdop=round(hdop_base * 1.45, 3),
            fix_type=fix_type,
            clock_bias_ns=round(clock_ns, 2),
            agc_level=round(agc, 3),
            visible_count=visible_count,
            position_error_m=round(pos_err, 2),
        )

        snapshot = GNSSSnapshot(
            timestamp=time.time(),
            satellites=self._satellites.copy(),
            receiver=receiver,
            avg_cn0=round(avg_cn0, 2),
            min_cn0=round(min_cn0, 2),
            std_cn0=round(std_cn0, 3),
            cn0_delta=round(avg_cn0 - self._prev_avg_cn0, 3),
            visible_count=visible_count,
            hdop=round(hdop_base, 3),
            pos_delta_m=round(pos_delta, 2),
            clock_offset_delta_ns=round(clock_delta, 3),
            doppler_residual=round(self._compute_doppler_residual(t_ms), 3),
            agc_level=round(agc, 3),
            true_label=self.attack_type if self.attack_intensity > 0.3 else "NOMINAL",
        )

        self._prev_avg_cn0 = avg_cn0
        self._prev_lat = lat
        self._prev_lon = lon
        self._prev_clock_ns = clock_ns

        return snapshot

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2) -> float:
        """Distance in meters between two lat/lon points."""
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        return R * 2 * math.asin(math.sqrt(a))
