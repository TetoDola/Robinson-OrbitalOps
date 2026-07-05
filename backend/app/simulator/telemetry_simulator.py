from __future__ import annotations

from ..models import TelemetrySnapshot
from .scenarios import DAY_MINUTES, SIMULATION_STEP_MINUTES, build_24h_snapshot, calculation_notes


class TelemetrySimulator:
    def __init__(self) -> None:
        self.elapsed_minutes = 0
        self.index = 0
        self.running = True
        self._latest = build_24h_snapshot(self.elapsed_minutes)
        self._history: list[TelemetrySnapshot] = [self._latest]

    @property
    def minute_of_day(self) -> int:
        return self.elapsed_minutes % DAY_MINUTES

    @property
    def orbit_number(self) -> int:
        return self.elapsed_minutes // 96

    @property
    def mission_clock(self) -> str:
        hours = self.minute_of_day // 60
        minutes = self.minute_of_day % 60
        return f"{hours:02d}:{minutes:02d}"

    @property
    def orbit_fraction(self) -> float:
        return round((self.minute_of_day % 96) / 96, 3)

    def reset(self) -> TelemetrySnapshot:
        self.elapsed_minutes = 0
        self.index = 0
        self.running = False
        self._latest = build_24h_snapshot(self.elapsed_minutes)
        self._history = [self._latest]
        return self.latest()

    def start(self) -> TelemetrySnapshot:
        self.running = True
        return self.latest()

    def stop(self) -> TelemetrySnapshot:
        self.running = False
        return self.latest()

    def latest(self) -> TelemetrySnapshot:
        return self._latest

    def history(self) -> list[TelemetrySnapshot]:
        return self._history[-96:]

    def notes(self) -> list[str]:
        return calculation_notes(self.elapsed_minutes)

    def advance(self) -> TelemetrySnapshot:
        self.elapsed_minutes += SIMULATION_STEP_MINUTES
        self.index = (self.elapsed_minutes // SIMULATION_STEP_MINUTES) % (DAY_MINUTES // SIMULATION_STEP_MINUTES)
        self._latest = build_24h_snapshot(self.elapsed_minutes)
        self._history.append(self._latest)
        return self.latest()
