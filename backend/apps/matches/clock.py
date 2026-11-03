"""Persisted wall-clock deadlines; combat still resolves once per planning window."""

from datetime import datetime, timedelta

from apps.matches.defaults import DEFAULT_PHASE_DURATIONS

COMBAT_PHASES = {"BUILD_AND_SCOUT", "WAR", "FINAL_ASSAULT"}


def timestamp(value):
    return datetime.fromisoformat(value) if value else None


def phase_duration(config, phase):
    if is_continuous(config):
        return continuous_phase_duration(config, phase)
    return config.get("phase_durations", {}).get(phase, DEFAULT_PHASE_DURATIONS.get(phase, 0))


def open_planning_window(config, now):
    timer = config.setdefault("timer_state", {})
    timer["round_phase"] = "PLANNING"
    timer["round_started_at"] = now.isoformat()
    timer["next_round_at"] = (
        now + timedelta(seconds=config.get("round_duration_seconds", 30))
    ).isoformat()


def lifecycle_payload(match):
    """Use the same timer contract in snapshots, phase events and round events."""
    return {
        "status": match.status,
        "phase": match.phase,
        "current_round": match.configuration.get("current_round", 1),
        "timer_state": match.configuration.get("timer_state", {}),
        "round_phase": match.configuration.get("timer_state", {}).get("round_phase", "PLANNING"),
    }


def is_continuous(config):
    return config.get("gameplay_mode") == "CONTINUOUS"


def continuous_phase_duration(config, phase):
    if phase == "PREPARATION":
        return config.get("first_preparation_duration_seconds", 120) if config.get("current_round", 1) == 1 else config.get("preparation_duration_seconds", 180)
    if phase == "WAR":
        return config.get("battle_duration_seconds", 300)
    return 0


def open_continuous_phase(match, now):
    config = match.configuration
    timer = config.setdefault("timer_state", {})
    duration = continuous_phase_duration(config, match.phase)
    timer.update({"round_phase": "BATTLE" if match.phase == "WAR" else "PLANNING",
                  "phase_started_at": now.isoformat(),
                  "phase_ends_at": (now + timedelta(seconds=duration)).isoformat(),
                  "phase_remaining_seconds": duration})
    timer.pop("next_round_at", None)
    timer.pop("next_tick_at", None)
    timer["next_tick_at"] = (now + timedelta(milliseconds=config.get("battle_tick_interval_ms", 200))).isoformat()
