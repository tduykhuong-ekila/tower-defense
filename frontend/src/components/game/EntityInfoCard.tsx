import { towerSalePrice } from "../../game/towerSale";
import { UnitLevelStars } from "./UnitLevelStars";
import { MAX_UPGRADE_LEVEL } from "../../game/upgradeLevel";
import { useLayoutEffect, useRef, useState } from "react";
import { create } from "zustand";
import { useMatchStore } from "../../stores/matchStore";
import { UnitType } from "../../types/unit";
import { ENTITY_NAMES } from "../../game/entityArtwork";
import { EntityIllustration } from "./EntityIllustration";
import { teamIndex } from "../../game/map";
import { attackTargetInfo } from "../../game/attackTarget";

type Inspection = {id: string; x: number; y: number; pinned: boolean; catalog?: UnitType};
const useInspection = create<{current: Inspection | null}>(() => ({current: null}));
let hide: ReturnType<typeof setTimeout> | undefined;
export function inspectEntity(id: string | null, x: number, y: number, pinned = false, catalog?: UnitType) {
  clearTimeout(hide);
  if (id) useInspection.setState({current: {id, x, y, pinned, catalog}});
  else if (!useInspection.getState().current?.pinned)
    hide = setTimeout(() => useInspection.setState({current: null}), 120);
}
function dismiss() { clearTimeout(hide); useInspection.setState({current: null}); }
export function EntityInfoCard({hidden = false, onSell, sellDisabled = false, catalog = []}: {
  hidden?: boolean; onSell?: (id: string) => Promise<void>; sellDisabled?: boolean; catalog?: UnitType[];
}) {
  const {current} = useInspection();
  const entities = useMatchStore(s => s.entities);
  const teams = useMatchStore(s => s.teams);
  const currentTeamId = useMatchStore(s => s.currentTeamId);
  const entity = entities.find(e => e.id === current?.id);
  const team = teams.find(t => t.id === entity?.team_id);
  const map = useMatchStore(s => s.mapData);
  const teamUpgradeLevels = useMatchStore(s => s.teamUpgradeLevels);
  const ref = useRef<HTMLElement>(null);
  const [position, setPosition] = useState({left: 8, top: 8});
  useLayoutEffect(() => {
    // Hidden command/modal contexts must not leave a pinned card to reappear over the next UI.
    if (hidden && current) dismiss();
  }, [hidden, current]);
  useLayoutEffect(() => {
    if (!current || !ref.current) return;
    const place = () => {
      const {width, height} = ref.current!.getBoundingClientRect();
      const preferredX = current.x + 22 + width <= window.innerWidth ? current.x + 22 : current.x - width - 22;
      setPosition({left: Math.max(8, Math.min(preferredX, window.innerWidth - width - 8)),
        top: Math.max(8, Math.min(current.y + 16, window.innerHeight - height - 8))});
    };
    const observer = new ResizeObserver(place);
    observer.observe(ref.current);
    place(); window.addEventListener("resize", place);
    return () => { observer.disconnect(); window.removeEventListener("resize", place); };
  }, [current, entity?.id, hidden]);
  if (hidden || !current || (!entity && !current.catalog)) return null;
  const unit = current.catalog;
  const code = entity?.unit_code || unit!.code;
  const level = entity ? (teamUpgradeLevels[entity.team_id]?.[code] ?? entity.level) : (unit?.level ?? 1);
  const name = ENTITY_NAMES[code] || entity?.unit_name || unit?.name || code;
  const category = entity?.entity_kind || unit!.category;
  const hp = entity?.current_hp ?? unit!.hp, max = entity?.max_hp ?? unit!.hp;
  const target = entity ? attackTargetInfo(entity, entities, teams) : null;
  const stats = [
    ["Sát thương", entity?.damage ?? unit?.damage],
    ["Tầm bắn (node)", entity?.range ?? unit?.range],
    ...(entity?.attack_interval_seconds ? [["Giây / đòn", Number(entity.attack_interval_seconds.toFixed(2))]] : []),
    ...(category === "UNIT" ? [["Tốc độ di chuyển", entity?.movement_speed ?? unit?.movement_speed]] : []),

  ].filter(([, value]) => value !== undefined && value !== null);
  return <>
    {current.pinned && <button className="entity-inspect-dismiss" aria-label="Đóng thông tin đơn vị" onClick={dismiss} />}
    <aside className={`entity-info-card fantasy-frame ${current.pinned ? "pinned" : ""}`} ref={ref}
      style={position} role={current.pinned ? "dialog" : "tooltip"} aria-label={`Thông tin ${name}`}
      onKeyDown={e => {if (e.key === "Escape") dismiss();}}>
      <header><EntityIllustration code={code} name={name} category={category} level={level} teamIndex={entity ? Math.max(0, teamIndex(map, entity.team_id)) : 0} />
        <div><small>{category === "TOWER" ? "CÔNG SỰ PHÒNG THỦ" : "QUÂN CHIẾN ĐẤU"}</small><h3>{name}</h3><span>{team?.name || (unit ? "Thông số triển khai" : entity?.team_name)}</span></div>
        {current.pinned && <button aria-label="Đóng thẻ thông tin" onClick={dismiss}>×</button>}</header>
      <UnitLevelStars level={level} />
      {level >= MAX_UPGRADE_LEVEL && <strong> · CẤP TỐI ĐA</strong>}
      <div className="inspection-health"><span>HP <b>{hp} / {max}</b></span><div role="progressbar" aria-label="Máu" aria-valuenow={hp} aria-valuemax={max} aria-valuemin={0}><i style={{width: `${max ? Math.max(0, Math.min(100, hp / max * 100)) : 0}%`}} /></div></div>
      <dl>{stats.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      {entity && <section className="inspection-target" aria-label="Mục tiêu tấn công">
        <h4>Mục tiêu tấn công</h4>
        {target ? <>
          <strong>{target.name}</strong>
          <span>{target.teamName}{!target.id.startsWith("base:") && ` · #${target.id.slice(0, 8)}`}</span>
          <dl>
            <div><dt>HP mục tiêu</dt><dd>{target.hp} / {target.maxHp}</dd></div>
            {target.shield > 0 && <div><dt>Khiên mục tiêu</dt><dd>{target.shield}</dd></div>}
          </dl>
        </> : <p>Chưa có mục tiêu trong tầm tấn công</p>}
      </section>}
      {unit?.description && <p>{unit.description}</p>}
      {current.pinned && onSell && entity?.entity_kind === "TOWER" && entity.team_id === currentTeamId
        && ["ACTIVE", "DISABLED"].includes(entity.status) && entity.current_hp > 0 &&
        <button className="upgrade-button" disabled={sellDisabled}
          title="Giá xây gốc × HP còn lại / HP tối đa, làm tròn xuống"
          onClick={() => void onSell(entity.id)}>BÁN THÁP · +{towerSalePrice(entity, catalog.find(u => u.code === code)?.cost)} XU</button>}

    </aside>
  </>;
}
