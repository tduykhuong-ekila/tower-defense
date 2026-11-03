import type { ParticipantRole, Team } from '../types/match';

export function teamJoinIssue(team: Team, role: ParticipantRole, maximum: number): string | null {
  if ((team.members?.length || 0) >= maximum) return 'Đội đã đầy';
  if (role === 'MENTOR' && team.members?.some(member => member.role === 'MENTOR')) {
    return 'Đội đã có Mentor';
  }
  return null;
}

export function teamInvitationUrl(origin: string, roomCode: string, teamId: string): string {
  const url = new URL('/join', origin);
  url.searchParams.set('code', roomCode);
  url.searchParams.set('team', teamId);
  return url.toString();
}
