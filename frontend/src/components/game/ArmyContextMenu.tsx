import { useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { RenderEntity, RenderTeam } from '../../game/bridge';
import { ENTITY_NAMES } from '../../game/entityArtwork';
import { useModalFocus } from '../useModalFocus';

export function ArmyContextMenu({position, selected, enemies, canRetarget, canRetreat, disabled, onDefend,
  onClose, onAttack, onRetreat, onClear, targetsOnly = false}: {
  onDefend?: () => void;
  targetsOnly?: boolean;
  position: {x: number; y: number}; selected: RenderEntity[]; enemies: RenderTeam[];
  canRetarget: boolean; canRetreat: boolean; disabled: boolean;
  onClose: () => void; onAttack: (target: string) => void; onRetreat: () => void; onClear: () => void;
}) {
  const root = useRef<HTMLDivElement>(null);
  const [point, setPoint] = useState(position);
  useModalFocus(true, root, onClose);
  useLayoutEffect(() => {
    const place = () => {
      const rect = root.current?.getBoundingClientRect();
      if (rect) setPoint({
        x: Math.max(8, Math.min(position.x, window.innerWidth - rect.width - 8)),
        y: Math.max(8, Math.min(position.y, window.innerHeight - rect.height - 8)),
      });
    };
    place();
    window.addEventListener('resize', place);
    return () => window.removeEventListener('resize', place);
  }, [position]);
  const counts = new Map<string, number>();
  selected.forEach(unit => counts.set(unit.unit_code, (counts.get(unit.unit_code) || 0) + 1));
  const targets = enemies.filter(team => team.status === 'ACTIVE' && team.base_hp > 0);
  return createPortal(<div className="army-context-backdrop" onPointerDown={event => {
    if (event.target === event.currentTarget) { event.preventDefault(); onClose(); }
  }} onContextMenu={event => {event.preventDefault(); onClose();}}>
    <div ref={root} role="dialog" aria-modal="true" aria-label={targetsOnly ? "Chọn mục tiêu tấn công" : "Lệnh cho quân đã chọn"} tabIndex={-1}
      className="fantasy-frame army-context-menu" style={{left: point.x, top: point.y}}
      onContextMenu={event => {event.preventDefault(); event.stopPropagation();}}>
      <header><strong>{targetsOnly ? "Tấn công" : "Chỉ huy"} · {selected.length} quân</strong><button aria-label="Đóng menu chỉ huy" onClick={onClose}>✕</button></header>
      <small>{[...counts].map(([code, count]) => `${count} ${ENTITY_NAMES[code] || code}`).join(' · ')}</small>
      <div className="army-context-targets" role="group" aria-label="Tấn công căn cứ">
        <strong>Tấn công</strong>
        {targets.map(team => <button key={team.id} disabled={disabled || !canRetarget || !selected.some(unit =>
          unit.target_team_id !== team.id || ['RETREAT', 'AT_RALLY'].includes(unit.simulation_state?.order || ''))}
          onClick={() => onAttack(team.id)}>Tấn công → {team.name}</button>)}
        {!targets.length && <small>Không có căn cứ địch khả dụng.</small>}
      </div>
      {!targetsOnly && <>{onDefend && <button type="button" className="army-selected-defend"
          disabled={disabled || !canRetreat || !selected.some(unit => unit.simulation_state?.order !== 'DEFEND_BASE')}
          onClick={onDefend} title="Quay về căn cứ, tiêu diệt quân địch ở gần và tiếp tục phòng thủ.">Bảo vệ căn cứ</button>}
        <button disabled={disabled || !canRetreat || !selected.some(unit => !['RETREAT', 'AT_RALLY'].includes(unit.simulation_state?.order || ''))}
        onClick={onRetreat}>Rút về điểm tập kết</button>
      {!canRetreat && <small>Rút quân khả dụng từ giai đoạn giao tranh.</small>}
      <button onClick={onClear}>Bỏ chọn nhóm</button></>}
      {targetsOnly && <small>Bấm căn cứ để ra lệnh tấn công cho nhóm đã chọn.</small>}
      <small>Esc hoặc bấm bên ngoài để đóng.</small>
    </div>
  </div>, document.body);
}
