import type { Team } from '../types/match';

/** Only participants belonging to this team count; a mentor is optional. */
export function activeMemberCount(team: Team) {
  return (team.members || []).filter(member => member.team_id === team.id &&
    (member.role === 'MENTOR' || member.role === 'MENTEE')).length;
}
export function teamHasPlayers(team: Team) { return activeMemberCount(team) >= 1; }
