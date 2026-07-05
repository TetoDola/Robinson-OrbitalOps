from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

from ..models import (
    CheckpointStatus,
    GroundAckStatus,
    OrbitPhase,
    RandomSimulationConfig,
    SchedulerState,
    TelemetrySnapshot,
)


DAY_MINUTES = 24 * 60
ORBIT_PERIOD_MINUTES = 96
START_TIME = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def gaussian(value: float, center: float, width: float) -> float:
    return math.exp(-((value - center) / max(width, 1.0)) ** 2)


def orbit_phase_for(total_elapsed_minutes: int) -> OrbitPhase:
    orbit_number = total_elapsed_minutes // ORBIT_PERIOD_MINUTES
    orbit_fraction = (total_elapsed_minutes % ORBIT_PERIOD_MINUTES) / ORBIT_PERIOD_MINUTES
    if 0.18 <= orbit_fraction <= 0.31 and orbit_number % 3 in {1, 2}:
        return OrbitPhase.HIGH_RADIATION_ZONE
    if 0.58 <= orbit_fraction <= 0.90:
        return OrbitPhase.ECLIPSE
    if 0.52 <= orbit_fraction < 0.58 or orbit_fraction > 0.90:
        return OrbitPhase.TERMINATOR
    return OrbitPhase.SUNLIGHT


class RandomTelemetryGenerator:
    """Generates correlated, bounded telemetry for live agent testing."""

    def __init__(self, config: RandomSimulationConfig) -> None:
        self.config = config
        self.seed = config.seed if config.seed is not None else random.SystemRandom().randint(10_000, 999_999)
        self.random = random.Random(self.seed)
        self.elapsed_minutes = config.start_elapsed_minutes if config.start_elapsed_minutes is not None else self.random.randint(0, DAY_MINUTES - 1)
        self.index = 0
        self.running = config.auto_advance
        self._event_origin = self.elapsed_minutes + self.random.randint(35, 120)
        self._scenario_phase = {
            "thermal_ramp": self.random.randint(0, ORBIT_PERIOD_MINUTES * 8),
            "radiation_pass": self.random.randint(0, ORBIT_PERIOD_MINUTES * 5),
            "downlink_congestion": self.random.randint(0, ORBIT_PERIOD_MINUTES * 6),
            "scheduler_mismatch": self.random.randint(0, ORBIT_PERIOD_MINUTES * 7),
            "power_eclipse": self.random.randint(0, ORBIT_PERIOD_MINUTES * 4),
        }
        self._contact_phase = self.random.randint(0, ORBIT_PERIOD_MINUTES - 1)
        self._workload_demand = self.random.uniform(0.52, 0.84)
        self._ground_quality = self.random.uniform(0.62, 0.94)
        self._solar_weather = self.random.uniform(0.12, 0.34)
        self._thermal_degradation = self.random.uniform(0.0, 0.08)
        self._sensor_bias_c = self.random.uniform(-0.8, 0.8)
        self._battery_state = self.random.uniform(58, 82)
        self._gpu_temp_state = self.random.uniform(58, 72)
        self._radiator_temp_state = self.random.uniform(35, 45)
        self._ecc_corrected_total = self.random.randint(0, 5)
        self._ecc_uncorrected_total = 0
        self._radiation_accumulated = self.random.uniform(0.2, 2.0)
        self._latest = self._build_snapshot()
        self._history: list[TelemetrySnapshot] = [self._latest]

    @property
    def minute_of_day(self) -> int:
        return self.elapsed_minutes % DAY_MINUTES

    @property
    def orbit_number(self) -> int:
        return self.elapsed_minutes // ORBIT_PERIOD_MINUTES

    @property
    def mission_clock(self) -> str:
        minute = self.minute_of_day
        return f"{minute // 60:02d}:{minute % 60:02d}"

    @property
    def orbit_fraction(self) -> float:
        return round((self.elapsed_minutes % ORBIT_PERIOD_MINUTES) / ORBIT_PERIOD_MINUTES, 3)

    def latest(self) -> TelemetrySnapshot:
        return self._latest

    def history(self) -> list[TelemetrySnapshot]:
        return self._history[-144:]

    def start(self) -> TelemetrySnapshot:
        self.running = True
        return self.latest()

    def stop(self) -> TelemetrySnapshot:
        self.running = False
        return self.latest()

    def advance(self) -> TelemetrySnapshot:
        self.elapsed_minutes += self.config.step_minutes
        self.index += 1
        self._latest = self._build_snapshot()
        self._history.append(self._latest)
        return self.latest()

    def notes(self) -> list[str]:
        return [
            "Infinite random stream is bounded and correlated: workload drives power, power drives heat, orbit drives solar input, radiation drives ECC, and contact geometry drives downlink.",
            "LEO-like orbit period is 96 minutes with sunlight, terminator, eclipse, and high-radiation pass phases.",
            "Scenario pressures recur with seed-stable phases instead of one-shot events, so long runs keep realistic variation.",
            "Slow AR-style environment states model workload demand, ground-station quality, solar weather, sensor bias and thermal degradation.",
            "Battery integrates net watts over time instead of jumping independently.",
            "Generated values are synthetic and inspired by public spacecraft operations patterns, not proprietary NASA data.",
            f"Scenario={self.config.scenario}; seed={self.seed}; intensity={self.config.intensity:.2f}; noise={self.config.noise:.2f}.",
        ]

    def _pressure(self, scenario: str, center_offset: int, width: int) -> float:
        if self.config.scenario not in {scenario, "mixed"}:
            return 0.0
        periods = {
            "thermal_ramp": ORBIT_PERIOD_MINUTES * 7,
            "radiation_pass": ORBIT_PERIOD_MINUTES * 3,
            "downlink_congestion": ORBIT_PERIOD_MINUTES * 5,
            "scheduler_mismatch": ORBIT_PERIOD_MINUTES * 6,
            "power_eclipse": ORBIT_PERIOD_MINUTES * 4,
        }
        period = periods.get(scenario, ORBIT_PERIOD_MINUTES * 5)
        phase = (self.elapsed_minutes + self._scenario_phase.get(scenario, 0) + center_offset) % period
        primary = gaussian(phase, period * 0.36, width)
        secondary = 0.58 * gaussian(phase, period * 0.78, width * 1.55)
        background = 0.10 * (1 + math.sin((2 * math.pi * phase / period) + 0.7))
        return self.config.intensity * clamp(primary + secondary + background, 0.0, 1.0)

    def _noise(self, amplitude: float) -> float:
        return self.random.uniform(-amplitude, amplitude) * self.config.noise

    def _poissonish(self, rate: float) -> int:
        rate = max(0.0, rate)
        if rate < 0.25:
            return 1 if self.random.random() < rate else 0
        if rate < 18:
            limit = math.exp(-rate)
            product = 1.0
            count = 0
            while product > limit:
                count += 1
                product *= self.random.random()
            return max(0, count - 1)
        return max(0, int(round(self.random.gauss(rate, math.sqrt(rate)))))

    def _eta_to_phase(self, target: OrbitPhase) -> float | None:
        for offset in range(0, DAY_MINUTES + 1, self.config.step_minutes):
            if orbit_phase_for(self.elapsed_minutes + offset) == target:
                return float(offset)
        return None

    def _future_contacts(self) -> list[dict[str, float | int | str]]:
        contacts = []
        for offset in range(0, 360, self.config.step_minutes):
            contact = self._contact_geometry(self.elapsed_minutes + offset)
            if contact["seconds"] > 0:
                contacts.append(
                    {
                        "start_in_minutes": offset,
                        "duration_seconds": contact["seconds"],
                        "expected_mbps": round(contact["mbps"], 1),
                        "ground_station": contact["station"],
                    }
                )
            if len(contacts) == 3:
                break
        return contacts

    def _contact_geometry(self, elapsed_minutes: int) -> dict[str, float | int | str]:
        phase = ((elapsed_minutes + self._contact_phase) % ORBIT_PERIOD_MINUTES) / ORBIT_PERIOD_MINUTES
        station_index = (elapsed_minutes // ORBIT_PERIOD_MINUTES + self._contact_phase) % 4
        stations = ["Svalbard", "Alaska", "TrollSat", "Kourou"]
        visible = phase <= 0.12 or 0.48 <= phase <= 0.60 or (station_index == 0 and 0.78 <= phase <= 0.84)
        if not visible:
            return {"seconds": 0, "mbps": 0.0, "station": stations[station_index]}
        elevation = max(
            gaussian(phase, 0.06, 0.055),
            gaussian(phase, 0.54, 0.06),
            gaussian(phase, 0.81, 0.035) if station_index == 0 else 0,
        )
        seconds = int(clamp(360 + 780 * elevation * self._ground_quality, 180, 1050))
        mbps = clamp(12 + 48 * elevation * self._ground_quality + self._noise(4), 4, 72)
        return {"seconds": seconds, "mbps": mbps, "station": stations[station_index]}

    def _update_environment(self) -> None:
        orbit_wave = math.sin(2 * math.pi * self.elapsed_minutes / (ORBIT_PERIOD_MINUTES * 5))
        daily_wave = math.sin(2 * math.pi * self.minute_of_day / DAY_MINUTES)
        self._workload_demand = clamp(0.985 * self._workload_demand + 0.015 * (0.68 + 0.18 * orbit_wave) + self._noise(0.03), 0.18, 0.98)
        self._ground_quality = clamp(0.992 * self._ground_quality + 0.008 * (0.75 + 0.16 * daily_wave) + self._noise(0.025), 0.32, 1.0)
        self._solar_weather = clamp(0.990 * self._solar_weather + 0.010 * (0.22 + 0.16 * max(0, daily_wave)) + self._noise(0.02), 0.02, 0.95)
        self._thermal_degradation = clamp(self._thermal_degradation + 0.0008 * self.config.intensity + self._noise(0.001), 0.0, 0.24)
        self._sensor_bias_c = clamp(0.995 * self._sensor_bias_c + self._noise(0.04), -1.8, 1.8)

    def _build_snapshot(self) -> TelemetrySnapshot:
        self._update_environment()
        phase = orbit_phase_for(self.elapsed_minutes)
        orbit_fraction = (self.elapsed_minutes % ORBIT_PERIOD_MINUTES) / ORBIT_PERIOD_MINUTES
        minute_of_day = self.minute_of_day

        thermal_pressure = self._pressure("thermal_ramp", 110, 75)
        radiation_pressure = max(
            self._pressure("radiation_pass", 70, 55),
            0.48 if phase == OrbitPhase.HIGH_RADIATION_ZONE else 0.0,
        )
        downlink_pressure = self._pressure("downlink_congestion", 90, 70)
        scheduler_pressure = self._pressure("scheduler_mismatch", 65, 50)
        power_pressure = self._pressure("power_eclipse", 85, 70)
        mixed_pressure = max(thermal_pressure, radiation_pressure, downlink_pressure, scheduler_pressure, power_pressure)

        if phase == OrbitPhase.ECLIPSE:
            sun_factor = 0.02
        elif phase == OrbitPhase.TERMINATOR:
            sun_factor = 0.32
        elif phase == OrbitPhase.HIGH_RADIATION_ZONE:
            sun_factor = 0.58
        else:
            sun_factor = 0.88 + 0.08 * math.sin(2 * math.pi * orbit_fraction)
        solar_incidence_angle = clamp(82 * (1 - sun_factor) + self._noise(5), 0, 180)
        solar_input = clamp(6800 * sun_factor + self._noise(280), 60, 7100)

        if scheduler_pressure > 0.62:
            scheduler_state = SchedulerState.IDLE
        elif self._battery_state < 20 or power_pressure > 0.82:
            scheduler_state = SchedulerState.PAUSED
        else:
            scheduler_state = SchedulerState.RUNNING

        base_utilization = 42 + 48 * self._workload_demand + 8 * math.sin(2 * math.pi * minute_of_day / 310)
        if scheduler_state == SchedulerState.IDLE and scheduler_pressure > 0.58:
            gpu_utilization = 88 + 7 * scheduler_pressure
        elif scheduler_state == SchedulerState.PAUSED:
            gpu_utilization = 12 + 16 * mixed_pressure
        else:
            gpu_utilization = base_utilization + 10 * thermal_pressure + 4 * self.random.random()
        gpu_utilization = clamp(gpu_utilization + self._noise(7), 2, 98)

        memory_total = 192.0
        memory_used = clamp(72 + 72 * self._workload_demand + 42 * mixed_pressure + 0.24 * gpu_utilization + self._noise(10), 32, memory_total)
        compute_power = clamp(780 + gpu_utilization * 31 + 460 * self._workload_demand + 720 * thermal_pressure + 280 * scheduler_pressure + self._noise(220), 650, 4550)
        contact = self._contact_geometry(self.elapsed_minutes)
        downlink_window_seconds = int(contact["seconds"])
        downlink_available_mbps = float(contact["mbps"])
        if downlink_window_seconds:
            downlink_available_mbps = clamp(downlink_available_mbps - 22 * downlink_pressure - (6 if phase == OrbitPhase.ECLIPSE else 0) + self._noise(4), 3, 72)
        downlink_power = 380 if downlink_window_seconds else 0
        thermal_control_power = 520 + 280 * thermal_pressure + 140 * max(0, self._gpu_temp_state - 82) / 20
        base_power = 1650 + 120 * math.sin(2 * math.pi * minute_of_day / DAY_MINUTES)
        spacecraft_draw = clamp(base_power + compute_power + thermal_control_power + downlink_power, 2500, 6800)

        battery_capacity_wh = 12_000.0
        net_power = solar_input - spacecraft_draw - 230 * power_pressure
        self._battery_state = clamp(self._battery_state + (net_power / battery_capacity_wh) * (self.config.step_minutes / 60) * 100, 8, 96)

        target_gpu_temp = clamp(41 + compute_power / 122 + 16 * thermal_pressure + 13 * self._thermal_degradation + (4 if phase == OrbitPhase.ECLIPSE else 0), 45, 107)
        target_radiator = clamp(29 + compute_power / 220 + 10 * thermal_pressure + 9 * self._thermal_degradation + (5 if phase == OrbitPhase.ECLIPSE else 0), 28, 75)
        self._gpu_temp_state = clamp(0.74 * self._gpu_temp_state + 0.26 * target_gpu_temp + self._noise(2) + self._sensor_bias_c * 0.08, 40, 108)
        self._radiator_temp_state = clamp(0.78 * self._radiator_temp_state + 0.22 * target_radiator + self._noise(1.5), 25, 78)
        board_temperature = clamp(self._gpu_temp_state - (10 + 6 * mixed_pressure) + self._noise(2), 35, 88)
        hbm_temperature = clamp(self._gpu_temp_state + 5 + 8 * thermal_pressure, 42, 112)
        coolant_loop_temperature = clamp(self._radiator_temp_state + 3 + 6 * thermal_pressure, 28, 82)

        dose_rate = clamp(0.08 + 2.5 * radiation_pressure + 1.1 * self._solar_weather * (1 if phase == OrbitPhase.HIGH_RADIATION_ZONE else 0.25) + 0.16 * self.random.random(), 0.02, 5.8)
        ecc_delta = self._poissonish(0.4 + 10.5 * radiation_pressure)
        uncorrected_delta = 1 if radiation_pressure > 0.86 and self.random.random() < 0.22 + 0.35 * self.config.intensity else 0
        self._ecc_corrected_total += ecc_delta
        self._ecc_uncorrected_total += uncorrected_delta
        self._radiation_accumulated += dose_rate * (self.config.step_minutes / 60)

        active_cuda = 0 if scheduler_pressure > 0.82 and self.random.random() < 0.45 else (1 if gpu_utilization > 20 else 0)
        scheduler_registered = 0 if scheduler_state in {SchedulerState.IDLE, SchedulerState.PAUSED} else active_cuda
        unowned_cuda = 1 if scheduler_state == SchedulerState.IDLE and gpu_utilization > 65 else max(0, active_cuda - scheduler_registered)
        accounting_status = "STALE" if active_cuda == 0 and gpu_utilization > 60 else "OK"

        checkpoint_status = CheckpointStatus.TRUSTED
        suffix = "TRUSTED"
        if self._ecc_uncorrected_total or radiation_pressure > 0.70:
            checkpoint_status = CheckpointStatus.SUSPECT
            suffix = "SUSPECT"
        elif radiation_pressure > 0.45:
            checkpoint_status = CheckpointStatus.UNKNOWN
            suffix = "UNKNOWN"
        checkpoint_index = 900 + self.elapsed_minutes // 120
        checkpoint_size = clamp(82 + 18 * mixed_pressure + self._noise(4), 70, 130)
        local_storage_free = clamp(282 - 0.030 * (self.elapsed_minutes % (DAY_MINUTES * 7)) - 62 * mixed_pressure + (24 if downlink_window_seconds else 0), 42, 340)
        ground_ack = GroundAckStatus.PENDING if checkpoint_status != CheckpointStatus.TRUSTED or downlink_window_seconds else GroundAckStatus.ACKED

        timestamp = START_TIME + timedelta(minutes=self.elapsed_minutes)
        return TelemetrySnapshot(
            timestamp=timestamp.isoformat().replace("+00:00", "Z"),
            mission_id="ORBIT-GPU-RANDOM",
            orbit_phase=phase,
            node_id="OGPU-SYNTH-LEO-1",
            job_id="TRAIN-NEMO-OMNI-SIM",
            scheduler_state=scheduler_state,
            gpu_utilization_percent=round(gpu_utilization, 1),
            gpu_memory_used_gb=round(memory_used, 1),
            gpu_memory_total_gb=memory_total,
            gpu_power_watts=round(compute_power, 1),
            gpu_temperature_celsius=round(self._gpu_temp_state, 1),
            board_temperature_celsius=round(board_temperature, 1),
            radiator_temperature_celsius=round(self._radiator_temp_state, 1),
            battery_percent=round(self._battery_state, 1),
            solar_input_watts=round(solar_input, 1),
            spacecraft_power_draw_watts=round(spacecraft_draw, 1),
            downlink_available_mbps=round(downlink_available_mbps, 1),
            downlink_window_seconds=downlink_window_seconds,
            ecc_corrected_errors=self._ecc_corrected_total,
            ecc_uncorrected_errors=self._ecc_uncorrected_total,
            radiation_dose_rate=round(dose_rate, 3),
            checkpoint_latest_id=f"CKPT-{checkpoint_index}-{suffix}",
            checkpoint_latest_status=checkpoint_status,
            checkpoint_latest_size_gb=round(checkpoint_size, 1),
            local_storage_free_gb=round(local_storage_free, 1),
            ground_ack_status=ground_ack,
            compute_node_power_watts=round(compute_power + 260, 1),
            active_cuda_process_count=active_cuda,
            scheduler_registered_process_count=scheduler_registered,
            active_cuda_processes_not_in_scheduler=unowned_cuda,
            time_since_last_job_end_seconds=round(60 + 980 * scheduler_pressure, 1) if scheduler_state == SchedulerState.IDLE else 0,
            memory_release_delta_gb_per_min=round(-0.05 + 0.18 * scheduler_pressure, 3),
            rank_progress_skew=round(0.08 + 0.65 * scheduler_pressure + 0.18 * thermal_pressure, 3),
            current_step_duration_seconds=round(1.8 + 1.2 * thermal_pressure + 0.8 * scheduler_pressure, 3),
            rolling_p95_step_duration_seconds=round(2.0 + 1.0 * thermal_pressure + 0.6 * scheduler_pressure, 3),
            nccl_warning_count=self._poissonish(0.1 + 3.2 * scheduler_pressure),
            interconnect_error_rate=round(0.001 + 0.18 * scheduler_pressure + self.config.noise * 0.005, 4),
            power_violation_time_delta_seconds=round(15 + 280 * power_pressure, 1),
            xid_error_count=self._poissonish(0.05 + 1.8 * thermal_pressure),
            hbm_temperature_c=round(hbm_temperature, 1),
            coolant_loop_temperature_c=round(coolant_loop_temperature, 1),
            radiator_area_m2=8.6,
            radiator_emissivity=0.82,
            radiator_view_factor=0.78,
            sun_exposure_factor=round(sun_factor, 3),
            spacecraft_base_power_watts=round(base_power, 1),
            compute_power_watts=round(compute_power, 1),
            thermal_control_power_watts=round(thermal_control_power, 1),
            downlink_power_watts=round(downlink_power, 1),
            battery_capacity_wh=battery_capacity_wh,
            solar_incidence_angle_deg=round(solar_incidence_angle, 1),
            eclipse_eta_minutes=self._eta_to_phase(OrbitPhase.ECLIPSE),
            radiation_window_eta_minutes=self._eta_to_phase(OrbitPhase.HIGH_RADIATION_ZONE),
            critical_downlink_eta_minutes=float(next((offset for offset in range(0, 360, self.config.step_minutes) if self._contact_geometry(self.elapsed_minutes + offset)["seconds"] > 0), 360)),
            pcie_replay_count=self._poissonish(0.3 + 4.4 * scheduler_pressure),
            nvlink_error_count=self._poissonish(0.2 + 3.5 * scheduler_pressure),
            process_accounting_status=accounting_status,
            bandwidth_drop_percent=round(12 + 58 * downlink_pressure if downlink_window_seconds else 0, 1),
            stale_telemetry_seconds=round(10 + 210 * scheduler_pressure if accounting_status != "OK" else 0, 1),
            thermal_throttle_flag=self._gpu_temp_state > 92 or hbm_temperature > 100,
            radiation_dose_accumulated=round(self._radiation_accumulated, 3),
            orbital_latitude_deg=round(51.6 * math.sin(2 * math.pi * orbit_fraction), 2),
            altitude_km=round(410 + self._noise(8), 2),
            south_atlantic_anomaly_flag=phase == OrbitPhase.HIGH_RADIATION_ZONE,
            solar_particle_event_index=round(0.2 + 7.5 * radiation_pressure, 3),
            ecc_corrected_delta=ecc_delta,
            ecc_uncorrected_delta=uncorrected_delta,
            checkpoint_hash_verified=checkpoint_status == CheckpointStatus.TRUSTED,
            canary_eval_score=round(clamp(0.992 - 0.11 * radiation_pressure - 0.06 * uncorrected_delta, 0, 1), 3),
            last_trusted_checkpoint_age_minutes=round(12 + 170 * (1 if checkpoint_status != CheckpointStatus.TRUSTED else 0) + 30 * mixed_pressure, 1),
            future_contact_windows=self._future_contacts(),
            checkpoint_full_size_gb=round(checkpoint_size, 1),
            checkpoint_delta_size_gb=round(14 + 8 * mixed_pressure, 1),
            manifest_size_gb=0.05,
            hashes_size_gb=0.1,
            ecc_logs_size_gb=round(0.3 + 0.4 * radiation_pressure, 2),
            thermal_logs_size_gb=round(0.5 + 0.5 * thermal_pressure, 2),
            workload_logs_size_gb=round(0.6 + 0.7 * scheduler_pressure, 2),
            bit_error_rate=round(1e-10 + 8e-8 * radiation_pressure, 10),
            compression_ratio_estimate=round(clamp(0.42 - 0.08 * mixed_pressure, 0.2, 0.75), 3),
        )
