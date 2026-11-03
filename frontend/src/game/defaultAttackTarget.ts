type TargetTeam = { id: string; status: string };

/** Follow team order in a ring, retaining any valid player selection. */
export function resolveAttackTarget(
  teams: readonly TargetTeam[], teamId: string | null, selectedTarget: string,
): string {
  const ownIndex = teams.findIndex(team => team.id === teamId);
  // Wait for the player's assignment before choosing an initial opponent.
  if (ownIndex < 0) return "";
  const isEnemy = (team: TargetTeam) => team.id !== teamId && team.status === "ACTIVE";
  if (teams.some(team => team.id === selectedTarget && isEnemy(team))) return selectedTarget;
  for (let offset = 1; offset < teams.length; offset++) {
    const candidate = teams[(ownIndex + offset) % teams.length];
    if (isEnemy(candidate)) return candidate.id;
  }
  return "";
}
