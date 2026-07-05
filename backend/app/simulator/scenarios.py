from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from ..models import (
    CheckpointStatus,
    GroundAckStatus,
    OrbitPhase,
    SchedulerState,
    TelemetrySnapshot,
    utc_now,
)


SCENARIO_NAME = "radiation_thermal_downlink_collision"
DAY_MINUTES = 24 * 60
ORBIT_PERIOD_MINUTES = 96
SIMULATION_STEP_MINUTES = 15
START_TIME = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def gaussian(minute_of_day: int, center: int, width: int) -> float:
    return math.exp(-((minute_of_day - center) / width) ** 2)


def orbit_phase_for(minute_of_day: int) -> OrbitPhase:
    orbit_number = minute_of_day // ORBIT_PERIOD_MINUTES
    orbit_fraction = (minute_of_day % ORBIT_PERIOD_MINUTES) / ORBIT_PERIOD_MINUTES
    radiation_pass = 0.18 <= orbit_fraction <= 0.31 and orbit_number % 3 in {1, 2}
    if radiation_pass:
        return OrbitPhase.HIGH_RADIATION_ZONE
    if 0.58 <= orbit_fraction <= 0.9:
        return OrbitPhase.ECLIPSE
    if 0.52 <= orbit_fraction < 0.58 or orbit_fraction > 0.9:
        return OrbitPhase.TERMINATOR
    return OrbitPhase.SUNLIGHT


def build_24h_snapshot(total_elapsed_minutes: int) -> TelemetrySnapshot:
    minute_of_day = total_elapsed_minutes % DAY_MINUTES
    orbit_number = total_elapsed_minutes // ORBIT_PERIOD_MINUTES
    orbit_fraction = (minute_of_day % ORBIT_PERIOD_MINUTES) / ORBIT_PERIOD_MINUTES
    phase = orbit_phase_for(minute_of_day)
    primary_collision = gaussian(minute_of_day, 390, 105)
    secondary_collision = gaussian(minute_of_day, 1020, 90) * 0.62
    collision_pressure = max(primary_collision, secondary_collision)

    if phase == OrbitPhase.ECLIPSE:
        sun_factor = 0.02
    elif phase == OrbitPhase.TERMINATOR:
        sun_factor = 0.34
    elif phase == OrbitPhase.HIGH_RADIATION_ZONE:
        sun_factor = 0.62
    else:
        sun_factor = 0.92 + 0.06 * math.sin(2 * math.pi * orbit_fraction)

    solar_input = clamp(6600 * sun_factor, 70, 6700)
    day_battery_wave = 12 * math.sin(2 * math.pi * (minute_of_day - 160) / DAY_MINUTES)
    battery = clamp(64 + day_battery_wave + 11 * (sun_factor - 0.5) - 29 * collision_pressure, 14, 94)
    downlink_pass = minute_of_day % 180 <= 30
    downlink_seconds = 900 if downlink_pass else 0
    downlink_mbps = 0 if not downlink_pass else clamp(26 - 8 * collision_pressure - (5 if phase == OrbitPhase.ECLIPSE else 0), 8, 28)

    ecc_corrected = int(2 + 58 * primary_collision + 28 * secondary_collision + (12 if phase == OrbitPhase.HIGH_RADIATION_ZONE else 0))
    ecc_uncorrected = 1 if primary_collision > 0.72 or secondary_collision > 0.92 else 0

    if battery < 22:
        scheduler_state = SchedulerState.PAUSED
    elif collision_pressure > 0.78:
        scheduler_state = SchedulerState.IDLE
    else:
        scheduler_state = SchedulerState.RUNNING

    if scheduler_state == SchedulerState.IDLE and collision_pressure > 0.78:
        gpu_utilization = 92 + 3 * math.sin(total_elapsed_minutes / 25)
    elif scheduler_state == SchedulerState.PAUSED:
        gpu_utilization = 18 + 16 * collision_pressure
    else:
        gpu_utilization = 82 + 8 * math.sin(2 * math.pi * minute_of_day / 240) - 10 * max(0, 35 - battery) / 35
    gpu_utilization = clamp(gpu_utilization, 2, 97)

    gpu_memory_total = 192.0
    gpu_memory_used = clamp(128 + 28 * collision_pressure + (8 if scheduler_state == SchedulerState.PAUSED else 0), 42, gpu_memory_total)
    gpu_power = clamp(1050 + gpu_utilization * 31 + 610 * collision_pressure, 980, 4250)
    spacecraft_draw = clamp(2550 + gpu_power + (470 if downlink_pass else 0), 3200, 6000)
    radiator_temperature = clamp(38 + gpu_power / 185 + 12 * collision_pressure + (5 if phase == OrbitPhase.ECLIPSE else 0), 34, 68)
    gpu_temperature = clamp(51 + gpu_power / 130 + 21 * collision_pressure + (4 if phase == OrbitPhase.ECLIPSE else 0), 55, 101)
    board_temperature = clamp(gpu_temperature - (12 + 8 * collision_pressure), 43, 74)

    checkpoint_index = 880 + minute_of_day // 120
    if ecc_uncorrected or collision_pressure > 0.55:
        checkpoint_status = CheckpointStatus.SUSPECT
        checkpoint_suffix = "SUSPECT"
    elif phase == OrbitPhase.HIGH_RADIATION_ZONE and ecc_corrected > 20:
        checkpoint_status = CheckpointStatus.UNKNOWN
        checkpoint_suffix = "UNKNOWN"
    else:
        checkpoint_status = CheckpointStatus.TRUSTED
        checkpoint_suffix = "TRUSTED"

    local_storage_free = clamp(246 - (minute_of_day / DAY_MINUTES) * 74 - 42 * collision_pressure + (18 if downlink_pass else 0), 58, 260)
    ground_ack = GroundAckStatus.PENDING if checkpoint_status != CheckpointStatus.TRUSTED or downlink_pass else GroundAckStatus.ACKED
    simulated_time = START_TIME + timedelta(minutes=total_elapsed_minutes)

    return TelemetrySnapshot(
        timestamp=simulated_time.isoformat().replace("+00:00", "Z"),
        mission_id="ORBIT-GPU-01",
        orbit_phase=phase,
        node_id="OGPU-AURORA-7",
        job_id="TRAIN-LM-742",
        scheduler_state=scheduler_state,
        gpu_utilization_percent=round(gpu_utilization, 1),
        gpu_memory_used_gb=round(gpu_memory_used, 1),
        gpu_memory_total_gb=gpu_memory_total,
        gpu_power_watts=round(gpu_power, 1),
        gpu_temperature_celsius=round(gpu_temperature, 1),
        board_temperature_celsius=round(board_temperature, 1),
        radiator_temperature_celsius=round(radiator_temperature, 1),
        battery_percent=round(battery, 1),
        solar_input_watts=round(solar_input, 1),
        spacecraft_power_draw_watts=round(spacecraft_draw, 1),
        downlink_available_mbps=round(downlink_mbps, 1),
        downlink_window_seconds=downlink_seconds,
        ecc_corrected_errors=ecc_corrected,
        ecc_uncorrected_errors=ecc_uncorrected,
        radiation_dose_rate=round(0.12 + 1.85 * collision_pressure + (0.85 if phase == OrbitPhase.HIGH_RADIATION_ZONE else 0), 2),
        checkpoint_latest_id=f"CKPT-{checkpoint_index}-{checkpoint_suffix}",
        checkpoint_latest_status=checkpoint_status,
        checkpoint_latest_size_gb=round(88 + 12 * collision_pressure, 1),
        local_storage_free_gb=round(local_storage_free, 1),
        ground_ack_status=ground_ack,
    )


def calculation_notes(total_elapsed_minutes: int) -> list[str]:
    minute_of_day = total_elapsed_minutes % DAY_MINUTES
    phase = orbit_phase_for(minute_of_day)
    return [
        "1 tick live = 15 simulated minutes; 96 ticks = 24 simulated hours.",
        "Orbit period = 96 minutes. Phase = minute_in_orbit / 96: sunlight, terminator, eclipse, or high-radiation pass.",
        "Solar input = 6600W x sun factor. Eclipse uses near-zero solar input; terminator uses partial solar input.",
        "Battery = base mission reserve + daily sinusoidal trend + solar contribution - collision pressure.",
        "Collision pressure is a deterministic Gaussian risk peak around 06:30 and a smaller evening pass around 17:00.",
        "GPU power is derived from utilization and collision pressure; temperatures follow power plus eclipse/collision heat penalties.",
        "ECC errors rise during radiation/collision windows; one uncorrected ECC event marks the checkpoint suspect.",
        "Downlink windows open every 180 simulated minutes for 15 to 30 minutes; capacity = Mbps x seconds / 8192.",
        f"Current minute of day: {minute_of_day}; current phase: {phase.value}.",
    ]


def scenario_snapshots() -> list[TelemetrySnapshot]:
    base = {
        "mission_id": "ORBIT-GPU-01",
        "node_id": "OGPU-AURORA-7",
        "job_id": "TRAIN-LM-742",
        "gpu_memory_total_gb": 192.0,
        "checkpoint_latest_size_gb": 96.0,
    }
    rows = [
        dict(
            orbit_phase=OrbitPhase.SUNLIGHT,
            scheduler_state=SchedulerState.RUNNING,
            gpu_utilization_percent=86,
            gpu_memory_used_gb=138,
            gpu_power_watts=3650,
            gpu_temperature_celsius=74,
            board_temperature_celsius=61,
            radiator_temperature_celsius=43,
            battery_percent=76,
            solar_input_watts=6200,
            spacecraft_power_draw_watts=5100,
            downlink_available_mbps=12,
            downlink_window_seconds=0,
            ecc_corrected_errors=2,
            ecc_uncorrected_errors=0,
            radiation_dose_rate=0.12,
            checkpoint_latest_id="CKPT-881-TRUSTED",
            checkpoint_latest_status=CheckpointStatus.TRUSTED,
            local_storage_free_gb=240,
            ground_ack_status=GroundAckStatus.ACKED,
        ),
        dict(
            orbit_phase=OrbitPhase.TERMINATOR,
            scheduler_state=SchedulerState.RUNNING,
            gpu_utilization_percent=88,
            gpu_memory_used_gb=144,
            gpu_power_watts=3820,
            gpu_temperature_celsius=88,
            board_temperature_celsius=64,
            radiator_temperature_celsius=52,
            battery_percent=67,
            solar_input_watts=3800,
            spacecraft_power_draw_watts=5400,
            downlink_available_mbps=10,
            downlink_window_seconds=0,
            ecc_corrected_errors=5,
            ecc_uncorrected_errors=0,
            radiation_dose_rate=0.24,
            checkpoint_latest_id="CKPT-882-HOT",
            checkpoint_latest_status=CheckpointStatus.TRUSTED,
            local_storage_free_gb=190,
            ground_ack_status=GroundAckStatus.PENDING,
        ),
        dict(
            orbit_phase=OrbitPhase.HIGH_RADIATION_ZONE,
            scheduler_state=SchedulerState.RUNNING,
            gpu_utilization_percent=90,
            gpu_memory_used_gb=151,
            gpu_power_watts=3920,
            gpu_temperature_celsius=91,
            board_temperature_celsius=66,
            radiator_temperature_celsius=57,
            battery_percent=58,
            solar_input_watts=2900,
            spacecraft_power_draw_watts=5600,
            downlink_available_mbps=8,
            downlink_window_seconds=0,
            ecc_corrected_errors=28,
            ecc_uncorrected_errors=0,
            radiation_dose_rate=1.15,
            checkpoint_latest_id="CKPT-883-RAD",
            checkpoint_latest_status=CheckpointStatus.UNKNOWN,
            local_storage_free_gb=135,
            ground_ack_status=GroundAckStatus.PENDING,
        ),
        dict(
            orbit_phase=OrbitPhase.HIGH_RADIATION_ZONE,
            scheduler_state=SchedulerState.IDLE,
            gpu_utilization_percent=94,
            gpu_memory_used_gb=158,
            gpu_power_watts=4050,
            gpu_temperature_celsius=97,
            board_temperature_celsius=67,
            radiator_temperature_celsius=62,
            battery_percent=46,
            solar_input_watts=1800,
            spacecraft_power_draw_watts=5700,
            downlink_available_mbps=8,
            downlink_window_seconds=0,
            ecc_corrected_errors=51,
            ecc_uncorrected_errors=1,
            radiation_dose_rate=2.2,
            checkpoint_latest_id="CKPT-884-SUSPECT",
            checkpoint_latest_status=CheckpointStatus.SUSPECT,
            local_storage_free_gb=102,
            ground_ack_status=GroundAckStatus.PENDING,
        ),
        dict(
            orbit_phase=OrbitPhase.HIGH_RADIATION_ZONE,
            scheduler_state=SchedulerState.IDLE,
            gpu_utilization_percent=92,
            gpu_memory_used_gb=160,
            gpu_power_watts=3990,
            gpu_temperature_celsius=96,
            board_temperature_celsius=68,
            radiator_temperature_celsius=64,
            battery_percent=39,
            solar_input_watts=1400,
            spacecraft_power_draw_watts=5800,
            downlink_available_mbps=18,
            downlink_window_seconds=720,
            ecc_corrected_errors=58,
            ecc_uncorrected_errors=1,
            radiation_dose_rate=1.9,
            checkpoint_latest_id="CKPT-884-SUSPECT",
            checkpoint_latest_status=CheckpointStatus.SUSPECT,
            local_storage_free_gb=88,
            ground_ack_status=GroundAckStatus.PENDING,
        ),
        dict(
            orbit_phase=OrbitPhase.ECLIPSE,
            scheduler_state=SchedulerState.PAUSED,
            gpu_utilization_percent=42,
            gpu_memory_used_gb=152,
            gpu_power_watts=2750,
            gpu_temperature_celsius=90,
            board_temperature_celsius=66,
            radiator_temperature_celsius=60,
            battery_percent=24,
            solar_input_watts=120,
            spacecraft_power_draw_watts=4700,
            downlink_available_mbps=14,
            downlink_window_seconds=480,
            ecc_corrected_errors=62,
            ecc_uncorrected_errors=1,
            radiation_dose_rate=1.1,
            checkpoint_latest_id="CKPT-884-SUSPECT",
            checkpoint_latest_status=CheckpointStatus.SUSPECT,
            local_storage_free_gb=78,
            ground_ack_status=GroundAckStatus.PENDING,
        ),
        dict(
            orbit_phase=OrbitPhase.ECLIPSE,
            scheduler_state=SchedulerState.PAUSED,
            gpu_utilization_percent=12,
            gpu_memory_used_gb=148,
            gpu_power_watts=2100,
            gpu_temperature_celsius=84,
            board_temperature_celsius=63,
            radiator_temperature_celsius=57,
            battery_percent=18,
            solar_input_watts=80,
            spacecraft_power_draw_watts=4200,
            downlink_available_mbps=10,
            downlink_window_seconds=360,
            ecc_corrected_errors=63,
            ecc_uncorrected_errors=1,
            radiation_dose_rate=0.8,
            checkpoint_latest_id="CKPT-884-SUSPECT",
            checkpoint_latest_status=CheckpointStatus.SUSPECT,
            local_storage_free_gb=74,
            ground_ack_status=GroundAckStatus.PENDING,
        ),
    ]
    return [TelemetrySnapshot(timestamp=utc_now(), **base, **row) for row in rows]
