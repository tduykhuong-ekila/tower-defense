"""Coin bounties credited only for a lethal hit against an enemy entity."""

KILL_REWARDS = {
    "infantry": 4,
    "tank": 7,
    "artillery": 9,
    "mg_tower": 8,
    "cannon_tower": 12,
}


def award_kill_reward(teams, attacker_team_id, target, events):
    amount = KILL_REWARDS.get(target.get("unit_type_code"), 0)
    if not amount or attacker_team_id == target.get("team_id") or attacker_team_id not in teams:
        return
    team = teams[attacker_team_id]
    team["coins"] = team.get("coins", 0) + amount
    events.append({
        "type": "KILL_REWARD_AWARDED",
        "team_id": attacker_team_id,
        "target_entity_id": str(target["id"]),
        "target_team_id": str(target["team_id"]),
        "unit_type": target["unit_type_code"],
        "amount": amount,
        "new_balance": team["coins"],
    })
