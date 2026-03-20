# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Traffic pattern models for dynamic simulation.

Defines time-varying traffic patterns (DDoS, flash crowds, diurnal cycles, etc.)
that can be applied during scenario execution to model realistic load conditions.
"""

from __future__ import annotations

import math
import random
from enum import Enum

from pydantic import BaseModel, Field


class TrafficPatternType(str, Enum):
    """Types of traffic patterns that can be simulated."""

    CONSTANT = "constant"
    RAMP = "ramp"
    SPIKE = "spike"
    WAVE = "wave"
    DDoS_VOLUMETRIC = "ddos_volumetric"
    DDoS_SLOWLORIS = "ddos_slowloris"
    FLASH_CROWD = "flash_crowd"
    DIURNAL = "diurnal"
    DIURNAL_WEEKLY = "diurnal_weekly"
    GROWTH_TREND = "growth_trend"


# Seeded RNG for reproducible jitter in DDoS patterns.
_rng = random.Random(42)


class TrafficPattern(BaseModel):
    """A time-varying traffic pattern applied during simulation.

    The ``multiplier_at`` method returns the traffic multiplier at any given
    second within the pattern's duration.  A multiplier of 1.0 represents
    normal (baseline) traffic; higher values represent proportional increases.
    """

    pattern_type: TrafficPatternType
    peak_multiplier: float = Field(
        description="Maximum traffic multiplier relative to baseline (1.0).",
    )
    duration_seconds: int = Field(
        default=300,
        description="Total duration of the traffic pattern in seconds.",
    )
    ramp_seconds: int = Field(
        default=0,
        description="Time in seconds to ramp from baseline to peak.",
    )
    sustain_seconds: int = Field(
        default=0,
        description="Time in seconds to sustain peak traffic after ramping up.",
    )
    cooldown_seconds: int = Field(
        default=0,
        description="Time in seconds to ramp back down from peak to baseline.",
    )
    wave_period_seconds: int = Field(
        default=60,
        description="Period of one full oscillation for WAVE patterns.",
    )
    burst_interval_seconds: int = Field(
        default=10,
        description="Interval between bursts for DDoS patterns.",
    )
    base_multiplier: float = Field(
        default=1.0,
        description="Output scaling factor applied to the final multiplier result.",
    )
    affected_components: list[str] = Field(
        default_factory=list,
        description="Component IDs affected by this pattern.  Empty means all.",
    )
    weekend_factor: float = Field(
        default=0.6,
        description="Weekend traffic as a fraction of weekday peak (0.0-1.0). Used by DIURNAL_WEEKLY.",
    )
    description: str = Field(
        default="",
        description="Human-readable description of the traffic pattern.",
    )

    def multiplier_at(self, t: int) -> float:
        """Return the traffic multiplier at time *t* (seconds from start).

        The returned value is always >= 1.0 (before ``base_multiplier``
        scaling).  If *t* falls outside ``[0, duration_seconds)``, the
        baseline multiplier 1.0 is returned (still scaled by
        ``base_multiplier``).
        """
        if t < 0 or t >= self.duration_seconds:
            return 1.0 * self.base_multiplier

        pt = self.pattern_type

        if pt == TrafficPatternType.CONSTANT:
            raw = self._constant()
        elif pt == TrafficPatternType.RAMP:
            raw = self._ramp(t)
        elif pt == TrafficPatternType.SPIKE:
            raw = self._spike(t)
        elif pt == TrafficPatternType.WAVE:
            raw = self._wave(t)
        elif pt == TrafficPatternType.DDoS_VOLUMETRIC:
            raw = self._ddos_volumetric(t)
        elif pt == TrafficPatternType.DDoS_SLOWLORIS:
            raw = self._ddos_slowloris(t)
        elif pt == TrafficPatternType.FLASH_CROWD:
            raw = self._flash_crowd(t)
        elif pt == TrafficPatternType.DIURNAL:
            raw = self._diurnal(t)
        elif pt == TrafficPatternType.DIURNAL_WEEKLY:
            raw = self._diurnal_weekly(t)
        elif pt == TrafficPatternType.GROWTH_TREND:
            raw = self._growth_trend(t)
        else:
            raw = 1.0

        return raw * self.base_multiplier

    # ------------------------------------------------------------------
    # Private helpers for each pattern type
    # ------------------------------------------------------------------

    def _constant(self) -> float:
        """CONSTANT: always return *peak_multiplier*."""
        return self.peak_multiplier

    def _ramp(self, t: int) -> float:
        """RAMP: linear up over *ramp_seconds*, sustain, then linear down.

        Timeline: [0, ramp) -> linear 1.0 to peak
                  [ramp, ramp+sustain) -> peak
                  [ramp+sustain, ramp+sustain+cooldown) -> linear peak to 1.0
                  beyond -> 1.0
        """
        ramp = self.ramp_seconds
        sustain = self.sustain_seconds
        cooldown = self.cooldown_seconds
        peak = self.peak_multiplier

        if ramp > 0 and t < ramp:
            # Linear ramp up from 1.0 to peak.
            return 1.0 + (peak - 1.0) * (t / ramp)

        t_after_ramp = t - ramp
        if t_after_ramp < sustain:
            return peak

        t_after_sustain = t_after_ramp - sustain
        if cooldown > 0 and t_after_sustain < cooldown:
            # Linear ramp down from peak to 1.0.
            return peak - (peak - 1.0) * (t_after_sustain / cooldown)

        return 1.0

    def _spike(self, t: int) -> float:
        """SPIKE: instant jump to peak at *ramp_seconds*, sustain, instant drop.

        Timeline: [0, ramp) -> 1.0 (baseline)
                  [ramp, ramp+sustain) -> peak
                  beyond -> 1.0
        """
        ramp = self.ramp_seconds
        sustain = self.sustain_seconds

        if ramp <= t < ramp + sustain:
            return self.peak_multiplier
        return 1.0

    def _wave(self, t: int) -> float:
        """WAVE: sinusoidal oscillation between 1.0 and *peak_multiplier*.

        Uses a sine wave shifted so that the output oscillates between
        1.0 (trough) and peak_multiplier (crest).
        """
        period = self.wave_period_seconds
        if period <= 0:
            return self.peak_multiplier

        amplitude = (self.peak_multiplier - 1.0) / 2.0
        midpoint = 1.0 + amplitude
        return midpoint + amplitude * math.sin(2.0 * math.pi * t / period)

    def _ddos_volumetric(self, t: int) -> float:
        """DDoS_VOLUMETRIC: fast ramp to peak in 10 s, then sustain with jitter.

        The ramp phase lasts a fixed 10 seconds (linear).  After that the
        multiplier holds at *peak_multiplier* with random +/-20 % jitter
        (seeded RNG for reproducibility).
        """
        peak = self.peak_multiplier
        ramp_duration = 10  # fixed 10-second ramp

        if t < ramp_duration:
            return 1.0 + (peak - 1.0) * (t / ramp_duration)

        # Sustain at peak with +/-20 % jitter.
        # Use t-derived seed for deterministic jitter without module-level state
        jitter = (((t * 2654435761) & 0xFFFFFFFF) / 0xFFFFFFFF - 0.5) * 0.40
        return max(1.0, peak * (1.0 + jitter))

    def _ddos_slowloris(self, t: int) -> float:
        """DDoS_SLOWLORIS: steady linear ramp over full duration.

        Connections increase slowly (not RPS bursts).  The multiplier
        increases linearly from 1.0 at t=0 to *peak_multiplier* at t=duration.
        """
        duration = self.duration_seconds
        if duration <= 0:
            return self.peak_multiplier
        return 1.0 + (self.peak_multiplier - 1.0) * (t / duration)

    def _flash_crowd(self, t: int) -> float:
        """FLASH_CROWD: exponential ramp up, then slow linear decay.

        Phase 1 (ramp): exponential curve from 1.0 to peak over *ramp_seconds*.
        Phase 2 (decay): linear decay from peak back to 1.0 over the remaining
        duration.
        """
        ramp = self.ramp_seconds
        peak = self.peak_multiplier

        if ramp > 0 and t < ramp:
            # Exponential ramp: 1.0 * e^(k*t) where k = ln(peak) / ramp
            # so that at t=ramp the value equals peak.
            k = math.log(peak) / ramp
            return math.exp(k * t)

        # Linear decay from peak to 1.0 over remaining duration.
        decay_duration = self.duration_seconds - ramp
        if decay_duration <= 0:
            return peak

        t_decay = t - ramp
        return peak - (peak - 1.0) * (t_decay / decay_duration)

    def _diurnal(self, t: int) -> float:
        """DIURNAL: 24 h sine wave compressed into *duration_seconds*.

        The curve is minimum (1.0) at the start and end of the window, and
        reaches *peak_multiplier* at the midpoint -- mimicking a natural
        day/night traffic cycle.
        """
        duration = self.duration_seconds
        if duration <= 0:
            return self.peak_multiplier

        # sin curve: 0 at t=0, peaks at t=duration/2, back to 0 at t=duration.
        amplitude = (self.peak_multiplier - 1.0) / 2.0
        midpoint = 1.0 + amplitude
        return midpoint - amplitude * math.cos(2.0 * math.pi * t / duration)

    def _diurnal_weekly(self, t: int) -> float:
        """DIURNAL_WEEKLY: realistic 24h cycle with weekend factor.

        Maps t=0 to Monday 00:00.  The daily cycle uses a sine wave that
        peaks between 11:00-14:00 and is at its minimum around 03:00.

        On weekends (Saturday/Sunday), the multiplier is reduced by
        ``self.weekend_factor`` (e.g. 0.6 means 60% of weekday peak).
        """
        peak = self.peak_multiplier
        weekend_factor = self.weekend_factor

        seconds_per_day = 86400
        seconds_per_week = seconds_per_day * 7

        # Normalise t into the week
        t_in_week = t % seconds_per_week
        day_of_week = t_in_week // seconds_per_day  # 0=Mon .. 6=Sun
        t_in_day = t_in_week % seconds_per_day
        hour_of_day = t_in_day / 3600.0

        # Daily sine curve: minimum at 03:00, peak at ~12:30
        # sin reaches -1 at 03:00 and +1 at 15:00, so we shift by 3h.
        # Phase: sin(2*pi*(hour - 3)/24 - pi/2) peaks at hour=9+(24/4)=15
        # We want peak around 11-14, so use: sin(2*pi*(hour - 3)/24 - pi/2)
        # Actually let's use a cosine centred at 12.5:
        # cos(2*pi*(hour - 12.5)/24) is +1 at 12.5 and -1 at 0.5
        phase = 2.0 * math.pi * (hour_of_day - 12.5) / 24.0
        daily_factor = 0.5 * (1.0 + math.cos(phase))  # 0..1, peak at 12.5

        # Apply weekend reduction
        is_weekend = day_of_week >= 5  # Saturday=5, Sunday=6
        if is_weekend:
            daily_factor *= weekend_factor

        # Map daily_factor [0..1] to [1.0 .. peak_multiplier]
        return 1.0 + (peak - 1.0) * daily_factor

    def _growth_trend(self, t: int) -> float:
        """GROWTH_TREND: exponential growth over time.

        Applies ``(1 + monthly_rate)^(elapsed_days / 30)`` where
        ``monthly_rate`` is stored in ``peak_multiplier`` (e.g. 0.1 for
        10% monthly growth).  The multiplier starts at 1.0 at t=0 and
        grows exponentially.
        """
        monthly_rate = self.peak_multiplier
        elapsed_days = t / 86400.0
        return math.pow(1.0 + monthly_rate, elapsed_days / 30.0)


# =====================================================================
# Factory functions
# =====================================================================


def create_ddos_volumetric(
    peak: float = 10.0,
    duration: int = 300,
) -> TrafficPattern:
    """Create a volumetric DDoS traffic pattern.

    Ramps to *peak* in 10 seconds, then sustains with random +/-20 % jitter.
    """
    return TrafficPattern(
        pattern_type=TrafficPatternType.DDoS_VOLUMETRIC,
        peak_multiplier=peak,
        duration_seconds=duration,
        description=f"Volumetric DDoS: {peak}x peak, {duration}s duration",
    )


def create_ddos_slowloris(
    peak: float = 5.0,
    duration: int = 300,
) -> TrafficPattern:
    """Create a Slowloris-style DDoS traffic pattern.

    Connections increase linearly from baseline to *peak* over the full
    *duration*, modelling a slow resource-exhaustion attack.
    """
    return TrafficPattern(
        pattern_type=TrafficPatternType.DDoS_SLOWLORIS,
        peak_multiplier=peak,
        duration_seconds=duration,
        description=f"Slowloris DDoS: {peak}x peak, linear ramp over {duration}s",
    )


def create_flash_crowd(
    peak: float = 8.0,
    ramp: int = 30,
    duration: int = 300,
) -> TrafficPattern:
    """Create a flash-crowd traffic pattern.

    Exponential ramp to *peak* over *ramp* seconds, then slow linear decay
    over the remaining duration.
    """
    return TrafficPattern(
        pattern_type=TrafficPatternType.FLASH_CROWD,
        peak_multiplier=peak,
        duration_seconds=duration,
        ramp_seconds=ramp,
        description=f"Flash crowd: {peak}x peak, {ramp}s exponential ramp, {duration}s total",
    )


def create_viral_event(
    peak: float = 15.0,
    duration: int = 300,
) -> TrafficPattern:
    """Create a viral-event traffic pattern.

    Uses a RAMP profile with 60 s ramp-up, 120 s sustain, and 120 s cooldown,
    modelling a sudden surge of interest (e.g. trending social-media post).
    """
    return TrafficPattern(
        pattern_type=TrafficPatternType.RAMP,
        peak_multiplier=peak,
        duration_seconds=duration,
        ramp_seconds=60,
        sustain_seconds=120,
        cooldown_seconds=120,
        description=f"Viral event: {peak}x peak, 60s ramp / 120s sustain / 120s cooldown",
    )


def create_diurnal(
    peak: float = 3.0,
    duration: int = 300,
) -> TrafficPattern:
    """Create a diurnal (day/night) traffic pattern.

    A 24-hour sine wave compressed into *duration* seconds.  Minimum at the
    start and end, peak at the midpoint.
    """
    return TrafficPattern(
        pattern_type=TrafficPatternType.DIURNAL,
        peak_multiplier=peak,
        duration_seconds=duration,
        description=f"Diurnal cycle: {peak}x peak, compressed into {duration}s",
    )


def create_diurnal_weekly(
    peak: float = 3.0,
    duration: int = 604800,
    weekend_factor: float = 0.6,
) -> TrafficPattern:
    """Create a diurnal weekly traffic pattern.

    Models a realistic 24h cycle with peak traffic between 11:00-14:00 and
    minimum around 03:00.  Weekend traffic is reduced by *weekend_factor*
    (e.g. 0.6 means 60% of weekday peak).

    Parameters
    ----------
    peak:
        Maximum traffic multiplier during weekday peak hours.
    duration:
        Total duration in seconds (default: 604800 = 7 days).
    weekend_factor:
        Weekend traffic as a fraction of weekday peak (0.0-1.0).
    """
    return TrafficPattern(
        pattern_type=TrafficPatternType.DIURNAL_WEEKLY,
        peak_multiplier=peak,
        duration_seconds=duration,
        weekend_factor=weekend_factor,
        description=(
            f"Diurnal weekly: {peak}x weekday peak, "
            f"{weekend_factor:.0%} weekend factor, {duration}s duration"
        ),
    )


def create_growth_trend(
    monthly_rate: float = 0.1,
    duration: int = 2592000,
) -> TrafficPattern:
    """Create an exponential growth trend traffic pattern.

    Models steady traffic growth over time using the formula:
    ``(1 + monthly_rate)^(elapsed_days / 30)``

    Parameters
    ----------
    monthly_rate:
        Monthly growth rate as a decimal (e.g. 0.1 for 10% monthly growth).
    duration:
        Total duration in seconds (default: 2592000 = 30 days).
    """
    return TrafficPattern(
        pattern_type=TrafficPatternType.GROWTH_TREND,
        peak_multiplier=monthly_rate,
        duration_seconds=duration,
        description=(
            f"Growth trend: {monthly_rate:.0%} monthly rate, "
            f"{duration // 86400}d duration"
        ),
    )
