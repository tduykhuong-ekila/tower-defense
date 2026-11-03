import { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { RoomConstraints } from '../types/match';

export function useRoomConstraints() {
  const [constraints, setConstraints] = useState<RoomConstraints | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    api.getRoomConstraints().then(data => { if (active) setConstraints(data); })
      .catch(() => { if (active) setError('Không thể tải giới hạn phòng. Vui lòng tải lại trang.'); });
    return () => { active = false; };
  }, []);
  return { constraints, error };
}

export function maxTeamOptions(constraints: RoomConstraints, minimum = 0) {
  const start = Math.max(constraints.min_teams_to_start, minimum);
  return Array.from({ length: Math.max(0, constraints.max_teams - start + 1) }, (_, i) => start + i);
}

export function MaximumTeamsSelect({ value, onChange, constraints, minimum = 0, error = '' }: {
  value?: number; onChange: (value: number) => void; constraints: RoomConstraints | null;
  minimum?: number; error?: string;
}) {
  return <label style={{ display: 'block', marginBottom: 16 }}>
    Maximum Teams
    <select aria-label="Maximum Teams" required disabled={!constraints}
      value={value ?? constraints?.default_max_teams ?? ''}
      onChange={e => onChange(Number(e.target.value))}
      style={{ width: '100%', padding: '10px 14px', marginTop: 6, background: '#0d1527', color: '#fff', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
      {!constraints && <option value="">Đang tải...</option>}
      {constraints && maxTeamOptions(constraints, minimum).map(n => <option key={n} value={n}>{n} Teams</option>)}
    </select>
    <small style={{ display: 'block', marginTop: 6, color: 'var(--text-muted)' }}>
      {error || 'Select the maximum number of teams allowed to join this room.'}
    </small>
  </label>;
}
