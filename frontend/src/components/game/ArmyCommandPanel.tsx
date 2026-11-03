import { useRef, useState } from 'react';
import type { RenderEntity, RenderTeam } from '../../game/bridge';
import { ENTITY_NAMES } from '../../game/entityArtwork';
import { useModalFocus } from '../useModalFocus';

export function ArmyCommandPanel({troops, selected, enemies, onAttack, onSelectedRetreat,
  onSelectGroup, onClear, multiple, onMultiple, selectionMode, onSelectionMode, disabled,
  onRetreat, retreatOpen, onRetreatOpen, retreatCount, canRetarget = true, canRetreat = true,
  onDefend, onUpgrade, upgradeDisabled = false, showToolbar = true}: {
  onDefend?: () => void;
  showToolbar?: boolean;
  troops: RenderEntity[]; selected: RenderEntity[]; enemies: RenderTeam[];
  onAttack: (targetId: string) => void; onSelectedRetreat: () => void;
  onSelectGroup: (ids: string[]) => void; onClear: () => void;
  multiple: boolean; onMultiple: () => void; selectionMode: boolean; onSelectionMode: () => void;
  disabled: boolean; onRetreat: () => void;
  retreatOpen: boolean; onRetreatOpen: (open: boolean) => void; retreatCount: number;
  canRetarget?: boolean; canRetreat?: boolean; onUpgrade?: () => void; upgradeDisabled?: boolean;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  const optionsDialog = useRef<HTMLDivElement>(null);
  const [optionsOpen, setOptionsOpen] = useState(false);
  useModalFocus(retreatOpen, dialog, () => onRetreatOpen(false));
  useModalFocus(optionsOpen, optionsDialog, () => setOptionsOpen(false));
  const counts = new Map<string, number>();
  for (const unit of selected) counts.set(unit.unit_code, (counts.get(unit.unit_code) || 0) + 1);
  const composition = [...counts].map(([code,count]) => `${count} ${ENTITY_NAMES[code] || code}`).join(' · ');
  const targets = enemies.filter(team => team.status === 'ACTIVE' && team.base_hp > 0);
  const retreatable = canRetreat && selected.some(unit => !['RETREAT', 'AT_RALLY'].includes(unit.simulation_state?.order || ''));
  const choose = (units: RenderEntity[]) => { onSelectGroup(units.map(unit => unit.id)); setOptionsOpen(false); };
  const atRally = troops.filter(unit => unit.simulation_state?.order === 'AT_RALLY');
  return <>
    {showToolbar && <section className={`army-command-panel army-map-command ${selected.length ? 'has-selection' : 'is-empty'}`} aria-label="Điều khiển quân đội">
      <header>
        <div className="army-map-summary" aria-live="polite">
          <strong>{selected.length ? `Đã chọn ${selected.length} quân` : 'Chọn quân trên map để chỉ huy.'}</strong>
          {!!selected.length && <small title={composition}>{composition}<span className="army-context-hint"> · Shift + kéo để chọn nhóm</span></small>}
        </div>
        <div className="army-map-tools">
          <button className="army-touch-tool" disabled={disabled} aria-pressed={multiple} onClick={onMultiple}
            title="Bật để chạm thêm hoặc bỏ từng quân khỏi nhóm; kéo vẫn di chuyển bản đồ.">
            Chọn thêm{multiple ? ' ✓' : ''}
          </button>
          <button className="army-touch-tool army-box-tool" disabled={disabled} aria-pressed={selectionMode} onClick={onSelectionMode}
            title="Bật rồi kéo một vùng trên map để chọn quân. Tự tắt sau khi chọn; chụm hai ngón vẫn thu phóng.">
            Khoanh vùng{selectionMode ? ' ✓' : ''}
          </button>
          <button disabled={disabled || !selected.length} onClick={onClear}>Bỏ chọn</button>
          <button disabled={disabled} className="army-options-button" aria-label="Tùy chọn chỉ huy" onClick={() => setOptionsOpen(true)}>⋯</button>
        </div>
      </header>
      {!!selected.length && <div className="army-direct-commands">
        <div className="army-attack-targets" role="group" aria-label="Tấn công căn cứ">
          <span className="army-action-label">TẤN CÔNG</span>
          <div className="army-target-list">
            {targets.map(team => <button key={team.id} type="button" className="army-target-command"
              disabled={disabled || !canRetarget || !selected.some(unit => unit.target_team_id !== team.id ||
                ['RETREAT', 'AT_RALLY'].includes(unit.simulation_state?.order || ''))}
              onClick={() => onAttack(team.id)} title={`Ra lệnh cho ${selected.length} quân tấn công ${team.name}`}>
              <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 16 15.5 4.5M9 4h7v7M4 10v6h6" /></svg>
              <span>Tấn công → {team.name}</span>
            </button>)}
            {!targets.length && <small>Không có căn cứ địch khả dụng.</small>}
          </div>
        </div>
        {onDefend && <button type="button" className="army-selected-defend"
          disabled={disabled || !canRetreat || !selected.some(unit => unit.simulation_state?.order !== 'DEFEND_BASE')}
          onClick={onDefend} title="Quay về căn cứ, tiêu diệt quân địch ở gần và tiếp tục phòng thủ.">Bảo vệ căn cứ</button>}
        <button type="button" className="army-selected-retreat" disabled={disabled || !retreatable}
          onClick={onSelectedRetreat} title={canRetreat ? 'Không hồi máu; quân vẫn chịu sát thương trên đường về.' : 'Rút quân khả dụng từ giai đoạn giao tranh.'}>
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M16 10H5m0 0 4-4m-4 4 4 4M5 4H3v12h2" /></svg>
          <span>Rút về điểm tập kết</span>
        </button>
      </div>}

    </section>}
    {optionsOpen && <div className="army-confirm-backdrop">
      <div className="fantasy-frame army-options-dialog" ref={optionsDialog} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="army-options-title">
        <header><h3 id="army-options-title">Tùy chọn chỉ huy</h3><button aria-label="Đóng tùy chọn chỉ huy" onClick={() => setOptionsOpen(false)}>✕</button></header>
        <button disabled={disabled || !troops.length} onClick={() => choose(troops)}>Chọn toàn quân ({troops.length})</button>
        {[...new Set(troops.map(unit => unit.unit_code))].map(code => {
          const units = troops.filter(unit => unit.unit_code === code);
          return <button key={code} disabled={disabled} onClick={() => choose(units)}>Chọn {ENTITY_NAMES[code] || code} ({units.length})</button>;
        })}
        <button disabled={disabled || !atRally.length} onClick={() => choose(atRally)}>Chọn quân đã tập kết ({atRally.length})</button>
        {onUpgrade && <button className="upgrade-button" disabled={disabled || upgradeDisabled} onClick={() => { setOptionsOpen(false); onUpgrade(); }}>Nâng cấp toàn đội</button>}
        {canRetreat && <button className="army-retreat" disabled={disabled || !troops.some(unit => !['RETREAT', 'AT_RALLY'].includes(unit.simulation_state?.order || ''))}
          onClick={() => {setOptionsOpen(false); onRetreatOpen(true);}}>Rút toàn quân…</button>}
        <small>Touchpad: kéo thường để di chuyển map; Shift + kéo để chọn nhóm, Shift/Ctrl/⌘ + click để thêm/bỏ quân. Click hai ngón để mở lệnh. Dùng được ở cả hai tab.</small>
        <small>Không dùng phím: bật Khoanh vùng rồi kéo để chọn nhóm; nút tự tắt sau khi chọn. Cảm ứng: Chọn thêm để thêm/bỏ quân, kéo thường di chuyển map.</small>
      </div>
    </div>}
    {retreatOpen && <div className="army-confirm-backdrop">
      <div className="fantasy-frame army-confirm" ref={dialog} tabIndex={-1} role="alertdialog" aria-modal="true" aria-labelledby="retreat-title" aria-describedby="retreat-description">
        <h3 id="retreat-title">Rút toàn quân về tập kết?</h3>
        <p id="retreat-description">Ra lệnh cho {retreatCount} quân về điểm tập kết. Không hồi máu; quân vẫn chịu sát thương trên đường về.</p>
        <p>Quân xuất sau khi mở xác nhận không bị ảnh hưởng. Có thể chọn quân để tấn công lại.</p>
        <div className="army-command-actions">
          <button onClick={() => onRetreatOpen(false)}>Hủy</button>
          <button className="gold-button" disabled={disabled || !retreatCount} onClick={onRetreat}>Xác nhận rút {retreatCount} quân</button>
        </div>
      </div>
    </div>}
  </>;
}
