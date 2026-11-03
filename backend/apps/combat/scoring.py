"""
Victory evaluation, score computation, and match finalization (§12, §19.13, D6, D11).
Pure scoring functions and authoritative ScoringService.
"""

import math
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from apps.combat.models import MatchResult
from apps.matches.clock import lifecycle_payload
from apps.matches.defaults import DEFAULT_SCORING_WEIGHTS
from apps.matches.models import Match, MatchPhase, MatchStatus
from apps.matches.services import MatchService
from apps.units.models import EntityCategory, EntityStatus, GameEntity


def calculate_team_score(
    team_data: Dict[str, Any],
    weights: Dict[str, int],
    damage_dealt_cap: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Computes score breakdown for a single team (§12.2, D11):
    - enemy_base_destroyed: +100
    - damage_dealt: +10 per 100 HP
    - remaining_hp: +5 per 100 HP
    - correct_answers: +3 per answer
    - surviving_towers: +5 per tower
    - remaining_coins: +1 per 10 coins
    """
    w_base_destroyed = weights.get("enemy_base_destroyed", 100)
    w_damage_100 = weights.get("damage_dealt_per_100", 10)
    w_hp_100 = weights.get("remaining_hp_per_100", 5)
    w_correct_ans = weights.get("correct_answer", 3)
    w_surviving_tower = weights.get("surviving_tower", 5)
    w_coins_10 = weights.get("remaining_coins_per_10", 1)

    bases_destroyed = int(team_data.get("bases_destroyed", 0))
    raw_damage = int(team_data.get("base_damage_dealt", 0))

    # D11: Damage dealt cap
    capped_damage = raw_damage
    if damage_dealt_cap is not None:
        capped_damage = min(raw_damage, damage_dealt_cap)

    remaining_hp = max(0, int(team_data.get("base_hp", 0)))
    correct_answers = int(team_data.get("correct_answers", 0))
    surviving_towers = int(team_data.get("surviving_towers", 0))
    remaining_coins = max(0, int(team_data.get("coins", 0)))

    pts_destroyed = bases_destroyed * w_base_destroyed
    pts_damage = math.floor(capped_damage / 100) * w_damage_100
    pts_hp = math.floor(remaining_hp / 100) * w_hp_100
    pts_answers = correct_answers * w_correct_ans
    pts_towers = surviving_towers * w_surviving_tower
    pts_coins = math.floor(remaining_coins / 10) * w_coins_10

    calc_score = pts_destroyed + pts_damage + pts_hp + pts_answers + pts_towers + pts_coins
    total_score = team_data.get("total_score") if "total_score" in team_data else calc_score

    return {
        "total_score": int(total_score),
        "bases_destroyed": bases_destroyed,
        "base_damage_dealt": capped_damage,
        "remaining_base_hp": remaining_hp,
        "correct_answers": correct_answers,
        "surviving_towers": surviving_towers,
        "remaining_coins": remaining_coins,
        "breakdown": {
            "bases_destroyed_pts": pts_destroyed,
            "damage_dealt_pts": pts_damage,
            "remaining_hp_pts": pts_hp,
            "correct_answers_pts": pts_answers,
            "surviving_towers_pts": pts_towers,
            "coins_pts": pts_coins,
        },
    }


def rank_teams(
    teams_stats: List[Dict[str, Any]],
    weights: Dict[str, int],
    total_initial_enemy_hp: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Ranks teams deterministically (§12.3, D6):
    1. Higher final score (DESC)
    2. More enemy bases destroyed (DESC)
    3. Higher remaining base HP (DESC)
    4. Higher remaining coins (DESC)
    5. Shared rank if all equal
    """
    scored_teams = []
    for t in teams_stats:
        score_info = calculate_team_score(t, weights, damage_dealt_cap=total_initial_enemy_hp)
        entry = dict(t)
        entry.update(score_info)
        scored_teams.append(entry)

    # Sort key: 1. total_score DESC, 2. bases_destroyed DESC, 3. remaining_base_hp DESC, 4. remaining_coins DESC
    def sort_key(item):
        return (
            -item["total_score"],
            -item["bases_destroyed"],
            -item["remaining_base_hp"],
            -item["remaining_coins"],
        )

    scored_teams.sort(key=sort_key)

    # Assign ranks with tie handling
    ranked_results = []
    for i, team in enumerate(scored_teams):
        if i > 0:
            prev = scored_teams[i - 1]
            if (
                team["total_score"] == prev["total_score"]
                and team["bases_destroyed"] == prev["bases_destroyed"]
                and team["remaining_base_hp"] == prev["remaining_base_hp"]
                and team["remaining_coins"] == prev["remaining_coins"]
            ):
                team["final_rank"] = prev["final_rank"]
            else:
                team["final_rank"] = i + 1
        else:
            team["final_rank"] = 1

        ranked_results.append(team)

    return ranked_results


def calculate_match_awards(
    ranked_teams: List[Dict[str, Any]],
    initial_base_hp: int = 500,
) -> List[Dict[str, Any]]:
    """
    Computes the 5 optional awards (§13 FR-10, D14).
    Awards are presentation-only by default and do not modify official scores
    unless `enable_award_bonus_score` is explicitly enabled.
    """
    if not ranked_teams:
        return []

    # 1. Best Strategist
    best_strat = max(
        ranked_teams,
        key=lambda t: (
            t.get("bases_destroyed", 0) * 1000
            + t.get("base_damage_dealt", 0) * 2
            + t.get("correct_answers", 0) * 10,
            t.get("total_score", 0),
        ),
    )

    # 2. Best Defense
    best_defense = max(
        ranked_teams,
        key=lambda t: (
            t.get("remaining_base_hp", 0) * 2
            + t.get("surviving_towers", 0) * 50,
            t.get("total_score", 0),
        ),
    )

    # 3. Best Comeback: team with base_hp <= 40% initial_hp that achieved best rank, or rank 2
    comeback_candidates = [
        t for t in ranked_teams if t.get("remaining_base_hp", 0) <= initial_base_hp * 0.4
    ]
    if comeback_candidates:
        best_comeback = min(
            comeback_candidates,
            key=lambda t: (t.get("final_rank", 999), -t.get("total_score", 0)),
        )
    else:
        best_comeback = ranked_teams[1] if len(ranked_teams) > 1 else ranked_teams[0]

    # 4. Knowledge Champion
    best_knowledge = max(
        ranked_teams,
        key=lambda t: (
            t.get("correct_answers", 0) * 100 + t.get("remaining_coins", 0),
            t.get("total_score", 0),
        ),
    )

    # 5. Mentor–Mentee Synergy
    best_synergy = max(
        ranked_teams,
        key=lambda t: (
            min(t.get("actions_count", 0), t.get("correct_answers", 0)) * 30
            + t.get("correct_answers", 0) * 15,
            t.get("total_score", 0),
        ),
    )

    return [
        {
            "id": "best_strategist",
            "name": "Bậc Thầy Chiến Thuật (Best Strategist)",
            "description": "Tấn công và triệt hạ căn cứ địch xuất sắc nhất.",
            "team_id": str(best_strat["team_id"]),
            "team_name": best_strat["team_name"],
            "score": best_strat.get("bases_destroyed", 0) * 1000 + best_strat.get("base_damage_dealt", 0) * 2,
        },
        {
            "id": "best_defense",
            "name": "Bức Tường Kiên Cố (Best Defense)",
            "description": "Bảo tồn căn cứ và duy trì tháp phòng thủ bền vững nhất.",
            "team_id": str(best_defense["team_id"]),
            "team_name": best_defense["team_name"],
            "score": best_defense.get("remaining_base_hp", 0) * 2 + best_defense.get("surviving_towers", 0) * 50,
        },
        {
            "id": "best_comeback",
            "name": "Màn Lội Ngược Dòng (Best Comeback)",
            "description": "Kiên cường phản công sau khi bị dồn vào thế khó.",
            "team_id": str(best_comeback["team_id"]),
            "team_name": best_comeback["team_name"],
            "score": best_comeback.get("total_score", 0),
        },
        {
            "id": "knowledge_champion",
            "name": "Nhà Thông Thái (Knowledge Champion)",
            "description": "Đóng góp trí tuệ vượt trội qua các câu hỏi chiến lược.",
            "team_id": str(best_knowledge["team_id"]),
            "team_name": best_knowledge["team_name"],
            "score": best_knowledge.get("correct_answers", 0),
        },
        {
            "id": "mentor_mentee_synergy",
            "name": "Hiệp Đồng Tác Chiến (Mentor–Mentee Synergy)",
            "description": "Sự phối hợp nhịp nhàng giữa Mentor và Mentee.",
            "team_id": str(best_synergy["team_id"]),
            "team_name": best_synergy["team_name"],
            "score": min(best_synergy.get("actions_count", 0), best_synergy.get("correct_answers", 0)),
        },
    ]


class ScoringService:
    """
    Authoritative server service to calculate scores, rankings, and finalize matches.
    """

    @classmethod
    @transaction.atomic
    def finalize_match(cls, match: Match) -> List[MatchResult]:
        """
        Creates immutable MatchResult snapshot for all teams in the match (§19.13).
        Idempotent: if already finalized, returns existing MatchResult records.
        Updates match status to FINISHED and phase to RESULTS.
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)

        # Check existing results
        existing_results = list(
            MatchResult.objects.filter(match=match_locked).order_by("final_rank")
        )
        if existing_results:
            return existing_results

        from apps.questions.timers import freeze_for_match
        freeze_for_match(match_locked, timezone.now())
        config = match_locked.configuration or {}
        weights = config.get("scoring_weights", DEFAULT_SCORING_WEIGHTS)
        teams = list(match_locked.teams.all())

        # Total initial enemy HP cap for D11
        total_initial_hp = sum(t.initial_base_hp for t in teams)
        avg_initial_hp = teams[0].initial_base_hp if teams else 500

        # Gather stats for each team
        teams_data = []
        for team in teams:
            # Active surviving towers
            surviving_towers_count = GameEntity.objects.filter(
                team=team,
                entity_kind=EntityCategory.TOWER,
                status=EntityStatus.ACTIVE,
            ).count()

            # Correct answers
            correct_answers_count = team.assigned_questions.filter(is_correct=True).count()

            # Total actions performed by team
            from apps.units.models import ActionStatus, GameAction
            actions_count = GameAction.objects.filter(
                team=team,
                status=ActionStatus.RESOLVED,
            ).count()

            combat_stats = config.get("combat_stats", {}).get(str(team.id), {})
            bases_destroyed = combat_stats.get("bases_destroyed", 0)
            base_damage_dealt = combat_stats.get("base_damage_dealt", 0)

            teams_data.append({
                "team_id": team.id,
                "team_name": team.name,
                "base_hp": team.base_hp,
                "coins": team.coins,
                "bases_destroyed": bases_destroyed,
                "base_damage_dealt": base_damage_dealt,
                "correct_answers": correct_answers_count,
                "surviving_towers": surviving_towers_count,
                "actions_count": actions_count,
            })

        # Rank all teams
        ranked_list = rank_teams(
            teams_data,
            weights=weights,
            total_initial_enemy_hp=total_initial_hp,
        )

        # Elimination victory takes precedence over accumulated score (§12.1).
        # Keep ordinary score/tie ranks among the remaining teams.
        winner_id = config.get("elimination_winner_id")
        if winner_id:
            winner = next(r for r in ranked_list if str(r["team_id"]) == winner_id)
            others = rank_teams(
                [t for t in teams_data if str(t["team_id"]) != winner_id],
                weights=weights, total_initial_enemy_hp=total_initial_hp,
            )
            winner["final_rank"] = 1
            for result in others:
                result["final_rank"] += 1
            ranked_list = [winner, *others]

        # Calculate optional awards (D14)
        awards = calculate_match_awards(ranked_list, initial_base_hp=avg_initial_hp)

        # Optional award bonus score if enabled
        enable_bonus = config.get("enable_award_bonus_score", False)
        bonus_pts = config.get("award_bonus_points", 25) if enable_bonus else 0
        if enable_bonus and bonus_pts > 0:
            award_team_ids = {a["team_id"] for a in awards}
            for r in ranked_list:
                if str(r["team_id"]) in award_team_ids:
                    r["total_score"] += bonus_pts

        # Persist immutable MatchResult records
        created_results = []
        for r in ranked_list:
            res = MatchResult.objects.create(
                match=match_locked,
                team_id=r["team_id"],
                final_rank=r["final_rank"],
                final_score=r["total_score"],
                bases_destroyed=r["bases_destroyed"],
                base_damage_dealt=r["base_damage_dealt"],
                correct_answers=r["correct_answers"],
                remaining_base_hp=r["remaining_base_hp"],
                remaining_coins=r["remaining_coins"],
                surviving_towers=r["surviving_towers"],
            )
            created_results.append(res)
        scores = {str(r["team_id"]): r["total_score"] for r in ranked_list}
        for team in teams:
            team.score = scores[str(team.id)]
        from apps.teams.models import Team
        Team.objects.bulk_update(teams, ["score"])

        # Update Match state and persist calculated awards in configuration
        now = timezone.now()
        match_locked.status = MatchStatus.FINISHED
        match_locked.phase = MatchPhase.RESULTS
        match_locked.ended_at = match_locked.ended_at or now
        config["awards"] = awards
        config.setdefault("timer_state", {})["round_phase"] = "RESULTS"
        match_locked.configuration = config
        match_locked.save(update_fields=["status", "phase", "ended_at", "configuration", "updated_at"])

        # Record events
        winners = [str(r["team_id"]) for r in ranked_list if r["final_rank"] == 1]
        winner_team_id = winners[0] if len(winners) == 1 else None
        MatchService.record_match_event(
            match_locked,
            event_type="MATCH_ENDED",
            payload={
                "ended_at": now.isoformat(),
                "winner_team_id": winner_team_id,
                "winner_team_ids": winners,
                "total_teams": len(ranked_list),
                "awards": awards,
                **lifecycle_payload(match_locked),
            },
        )

        MatchService.record_match_event(
            match_locked,
            event_type="LEADERBOARD_UPDATED",
            payload={
                "leaderboard": [
                    {
                        "rank": r["final_rank"],
                        "team_id": str(r["team_id"]),
                        "team_name": r["team_name"],
                        "score": r["total_score"],
                        "bases_destroyed": r["bases_destroyed"],
                        "base_damage_dealt": r["base_damage_dealt"],
                        "remaining_hp": r["remaining_base_hp"],
                        "coins": r["remaining_coins"],
                        "correct_answers": r["correct_answers"],
                        "surviving_towers": r["surviving_towers"],
                    }
                    for r in ranked_list
                ],
                "awards": awards,
            },
        )

        return created_results
