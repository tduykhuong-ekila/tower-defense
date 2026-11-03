"""
Default match configuration and constants.
Source: GDD_PRD.md §4.1, §7.4, §11, and Architectural Decisions D1-D12.
"""

DEFAULT_PHASE_DURATIONS = {
    "PREPARATION": 180,  # 3 minutes
    "BUILD_AND_SCOUT": 420,  # 7 minutes
    "WAR": 720,  # 12 minutes
    "FINAL_ASSAULT": 300,  # 5 minutes
    "RESULTS": 180,  # 3 minutes
}

DEFAULT_SCORING_WEIGHTS = {
    "enemy_base_destroyed": 100,
    "damage_dealt_per_100": 10,
    "remaining_hp_per_100": 5,
    "correct_answer": 3,
    "surviving_tower": 5,
    "remaining_coins_per_10": 1,
}

DEFAULT_SPECIAL_ACTIONS = {
    "scout": True,
    "emp": True,
    "repair": True,
    "upgrade": True,
}

DEFAULT_SPECIAL_ACTION_COSTS = {
    "scout": 10,
    "emp": 30,
    "repair": 20,
    "upgrade": 25,
}

MIN_TEAMS_TO_START = 2
MAX_TEAMS = 20
DEFAULT_MAX_TEAMS = 4
MIN_MEMBERS_PER_TEAM = 1
QUESTION_COIN_REWARD = 30

DEFAULT_MATCH_CONFIGURATION = {
    # New rooms use major rounds; stored rooms without gameplay_mode stay legacy.
    "gameplay_mode": "CONTINUOUS",
    "arena_layout_version": 7,
    "tower_placement_version": 1,
    "total_rounds": 3,
    "preparation_duration_seconds": 180,
    "first_preparation_duration_seconds": 120,
    "battle_duration_seconds": 300,
    "battle_tick_interval_ms": 200,
    "attack_cooldown_seconds": 2.0,
    "movement_baseline_round_seconds": 30,
    "troop_formation_gap": 2,
    "troop_target_priority": ["TOWER", "UNIT"],
    # Teams & Players (§4.1, D1, D2)
    "min_teams": MIN_TEAMS_TO_START,
    "max_teams": DEFAULT_MAX_TEAMS,
    "min_players_per_team": MIN_MEMBERS_PER_TEAM,
    "max_players_per_team": 4,
    # Base Stats (§4.1)
    "initial_base_hp": 500,
    "initial_coins": 100,
    # Match & Phase Timers (§4.1, §11)
    "match_duration_seconds": 1380,  # Three major rounds: 23 minutes total
    "phase_durations": DEFAULT_PHASE_DURATIONS,
    "round_duration_seconds": 30,  # D3: 30s planning window per combat round
    "reward_grace_period_seconds": 15,  # §11: 15s grace period
    # Economy & Questions (§4.1, §7.4)
    "max_questions_per_team": 8,
    "correct_answer_coin_reward": 30,  # Legacy fixed assignments only; new missions use mystery bags.
    "base_income_per_round": 10,
    # Units & Tower Limits (§4.1)
    "max_towers_per_team": None,  # Compatibility field: no tower quantity limit.
    "max_active_units_per_team": 5,
    "max_deployed_units_per_action": None,  # Coins and vehicle capacity bound each batch.
    "max_tower_placements_per_action": 1,
    # Scoring & Victory (§12.2)
    "scoring_weights": DEFAULT_SCORING_WEIGHTS,
    # Policies (§9.4, §16, D8)
    "fallback_policy": "RETARGET_NEAREST",  # "IDLE" | "RETARGET_NEAREST"
    "spectator_visibility": "FULL",  # "FULL" | "FOG_OF_WAR"
    "special_actions_enabled": DEFAULT_SPECIAL_ACTIONS,
    "special_action_costs": DEFAULT_SPECIAL_ACTION_COSTS,
    "allow_late_join": False,
}


def get_default_configuration() -> dict:
    """Return a deep copy of the default match configuration."""
    import copy

    return copy.deepcopy(DEFAULT_MATCH_CONFIGURATION)


MATCH_PRESETS = {
    "standard_30m": {
        "id": "standard_30m",
        "name": "Tiêu chuẩn (3 vòng · 23 phút)",
        "description": "3 vòng chính, chuẩn bị 120/180/180 giây và giao tranh liên tục 300 giây mỗi vòng.",
        "configuration": get_default_configuration(),
    },
    "quick_15m": {
        "id": "quick_15m",
        "name": "Nhanh (15 phút)",
        "description": "2 vòng chính, chuẩn bị 60 giây và giao tranh 390 giây mỗi vòng, 5 câu hỏi, 150 coin.",
        "configuration": {
            **get_default_configuration(),
            "total_rounds": 2,
            "first_preparation_duration_seconds": 60,
            "preparation_duration_seconds": 60,
            "battle_duration_seconds": 390,
            "match_duration_seconds": 900,
            "phase_durations": {
                "PREPARATION": 60,
                "BUILD_AND_SCOUT": 240,
                "WAR": 360,
                "FINAL_ASSAULT": 120,
                "RESULTS": 120,
            },
            "round_duration_seconds": 20,
            "max_questions_per_team": 5,
            "initial_coins": 150,
            "base_income_per_round": 15,
        },
    },
    "blitz_10m": {
        "id": "blitz_10m",
        "name": "Blitz Cao Trào (10 phút)",
        "description": "2 vòng chính trong 10 phút, chuẩn bị 45 giây, giao tranh 255 giây, 4 câu hỏi, 180 coin.",
        "configuration": {
            **get_default_configuration(),
            "total_rounds": 2,
            "first_preparation_duration_seconds": 45,
            "preparation_duration_seconds": 45,
            "battle_duration_seconds": 255,
            "match_duration_seconds": 600,
            "phase_durations": {
                "PREPARATION": 45,
                "BUILD_AND_SCOUT": 150,
                "WAR": 240,
                "FINAL_ASSAULT": 90,
                "RESULTS": 75,
            },
            "round_duration_seconds": 15,
            "max_questions_per_team": 4,
            "initial_coins": 180,
            "base_income_per_round": 20,
        },
    },
}


def calculate_balance_preview(config: dict) -> dict:
    """
    Computes projected economy & combat balance metrics for pre-match tuning (§7.4, FR-09).
    Allows the host to preview game economy before starting the match.
    """
    phase_durs = config.get("phase_durations", DEFAULT_PHASE_DURATIONS)
    combat_seconds = (
        phase_durs.get("BUILD_AND_SCOUT", 420)
        + phase_durs.get("WAR", 720)
        + phase_durs.get("FINAL_ASSAULT", 300)
    )
    round_sec = max(10, config.get("round_duration_seconds", 30))
    est_rounds = max(1, combat_seconds // round_sec)
    if config.get("gameplay_mode") == "CONTINUOUS":
        est_rounds = config.get("total_rounds", 3)
        round_sec = config.get("battle_duration_seconds", 300)

    income_per_round = config.get("base_income_per_round", 10)
    passive_coins = est_rounds * income_per_round
    init_coins = config.get("initial_coins", 100)
    max_q = config.get("max_questions_per_team", 8)
    from apps.rewards.coin_rewards import COIN_REWARD_DISTRIBUTION, EXPECTED_COIN_REWARD
    max_q_coins = max_q * max(amount for amount, _ in COIN_REWARD_DISTRIBUTION)
    expected_q_coins = max_q * EXPECTED_COIN_REWARD
    total_projected_coins = init_coins + passive_coins + expected_q_coins

    match_sec = config.get("match_duration_seconds", 1800)
    if config.get("gameplay_mode") == "CONTINUOUS":
        match_sec = config.get("first_preparation_duration_seconds", 120) + (est_rounds - 1) * config.get("preparation_duration_seconds", 180) + est_rounds * round_sec
    total_minutes = round(match_sec / 60, 1)

    return {
        "total_match_minutes": total_minutes,
        "estimated_combat_rounds": est_rounds,
        "round_duration_seconds": round_sec,
        "initial_coins": init_coins,
        "projected_passive_coins": passive_coins,
        "max_question_coins": max_q_coins,
        "expected_question_coins": expected_q_coins,
        "total_projected_coins_per_team": total_projected_coins,
        "initial_base_hp": config.get("initial_base_hp", 500),
        "max_towers_per_team": None,
        "max_active_units_per_team": config.get("max_active_units_per_team", 5),
        "pacing": "FAST" if total_minutes <= 15 else "STANDARD" if total_minutes <= 30 else "LONG",
    }

