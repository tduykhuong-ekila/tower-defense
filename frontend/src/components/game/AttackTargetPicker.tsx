import { useRef, useState } from 'react';
import type { RenderTeam } from '../../game/bridge';
import { useModalFocus } from '../useModalFocus';

/** Selection only: the caller owns the explicit deploy/retarget action. */
export function AttackTargetPicker({ enemies, target, title, onSelect, onClose }: {
  enemies: RenderTeam[]; target: string; title: string;
  onSelect: (id: string) => void; onClose: () => void;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState('');
  useModalFocus(true, dialog, onClose);
  const rows = enemies.filter(team => team.status === 'ACTIVE' && team.base_hp > 0 &&
    team.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return <div className="attack-target-backdrop">
    <div className="attack-target-dialog fantasy-frame" ref={dialog} tabIndex={-1}
      role="dialog" aria-modal="true" aria-labelledby="attack-target-title">
      <header><div><small>CHỌN ĐỐI THỦ</small><h2 id="attack-target-title">{title}</h2></div>
        <button className="target-close" onClick={onClose} aria-label="Đóng chọn mục tiêu">✕</button></header>
      <p>Chọn mục tiêu để chuẩn bị lệnh. Quân chỉ nhận lệnh khi bạn bấm nút thực hiện.</p>
      <input aria-label="Tìm đối thủ" placeholder="Tìm tên đối thủ…" value={query} onChange={e => setQuery(e.target.value)} />
      <div className="attack-target-rows">{rows.map(team => <button key={team.id}
        className={`attack-target-row ${team.id === target ? 'selected' : ''}`}
        aria-pressed={team.id === target} onClick={() => onSelect(team.id)}>
        <span className="attack-target-mark" aria-hidden="true">◎</span>
        <span><strong>{team.name}</strong><small>{team.base_hp} / {team.initial_base_hp} HP căn cứ</small></span>
        <span>{team.id === target ? '✓ Đang chọn' : 'Chọn'}</span>
      </button>)}</div>
      {!rows.length && <p role="status">Không có đối thủ phù hợp.</p>}
      <button className="target-cancel" onClick={onClose}>Hủy</button>
    </div>
  </div>;
}
