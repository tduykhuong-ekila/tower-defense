import { useRef, useState } from "react";
import { Coins } from "lucide-react";
import { UnitLevelStars } from "./UnitLevelStars";
import { MAX_UPGRADE_LEVEL, upgradeLevel } from "../../game/upgradeLevel";
import { UnitType } from "../../types/unit";
import { EntityIllustration } from "./EntityIllustration";
import { ENTITY_NAMES } from "../../game/entityArtwork";
import { useModalFocus } from "../useModalFocus";

const EQUIPMENT = ["Trang bị cơ bản", "Giáp và nền móng gia cố", "Giáp nặng và vũ khí cải tiến"];
const formatUpgradeStat = (label: string, value: number) =>
  ["Sát thương / đòn", "Tốc độ bắn", "Giây / đòn"].includes(label)
    ? value.toFixed(2)
    : String(value);
interface Props {
  units: UnitType[]; coins: number; teamIndex: number; disabled: boolean;
  selectedType?: string; onSelectType: (code: string) => void;
  onClose: () => void; onPurchase: (unit: UnitType, key: string) => Promise<void>;
}
export function TeamUpgradeModal({units, coins, teamIndex, disabled, selectedType, onSelectType, onClose, onPurchase}: Props) {
  const dialog = useRef<HTMLDivElement>(null);
  // Controlled by the intentional open/select action; live catalog updates never reset it.
  const selected = selectedType ?? units.find(u => u.upgrade?.eligible)?.code;
  const setSelected = (code: string) => onSelectType(code);
  const [confirming, setConfirming] = useState<string>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<{signature: string; key: string}>();
  useModalFocus(true, dialog, () => {if (!pending) onClose();});
  const unit = units.find(u => u.code === selected);
  const upgrade = unit?.upgrade;
  const level = upgradeLevel(unit?.level);
  const unlocked = unit?.is_unlocked || unit?.is_starter;
  const signature = `${selected}:${level}`;
  const canBuy = !!unit && !!upgrade?.eligible && level < MAX_UPGRADE_LEVEL && !!upgrade?.next_stats && unlocked && coins >= (upgrade.cost ?? Infinity) && !disabled && !pending;
  const buy = async () => {
    if (!canBuy || !unit) return;
    if (!request.current || request.current.signature !== signature)
      request.current = {signature, key: crypto.randomUUID()};
    setPending(true); setError("");
    try { await onPurchase(unit, request.current.key); setConfirming(undefined); }
    catch (e) {setError(e instanceof Error ? e.message : "Không thể nâng cấp.");}
    finally {setPending(false);}
  };
  const stats = upgrade?.current_stats, next = level < MAX_UPGRADE_LEVEL ? upgrade?.next_stats : undefined;
  return <div className="team-upgrade-overlay" ref={dialog} role="dialog" aria-modal="true" aria-label="Nâng cấp toàn đội" tabIndex={-1}>
    <section className="team-upgrade-panel fantasy-frame">
      <header><div><small>TRANG BỊ TOÀN ĐỘI</small><h2>NÂNG CẤP</h2></div><div className="team-upgrade-coins" aria-label={`${coins} xu hiện có`}><strong><Coins size={16} aria-hidden="true" />{coins.toLocaleString("vi-VN")}</strong></div><button aria-label="Đóng nâng cấp" disabled={pending} onClick={onClose}>×</button></header>
      <p className="upgrade-description">Nâng cấp này áp dụng cho toàn bộ đơn vị cùng loại của đội, bao gồm quân đã triển khai và quân xuất sau này.</p>
      <nav aria-label="Loại nâng cấp">{units.filter(u => u.upgrade?.eligible).slice().sort((a, b) => (a.category === b.category ? 0 : a.category === "UNIT" ? -1 : 1)).map(u => <button key={u.code} className={u.code === selected ? "active" : ""} aria-pressed={u.code === selected} data-upgrade-type={u.code} data-category={u.category} disabled={pending} onClick={() => {setSelected(u.code); setConfirming(undefined); setError("");}}>
        <EntityIllustration code={u.code} name={ENTITY_NAMES[u.code] || u.name} category={u.category} teamIndex={teamIndex} level={u.level} />
        <span>{ENTITY_NAMES[u.code] || u.name}</span> <UnitLevelStars level={u.level} size="compact" /></button>)}</nav>
      {!unit && <article aria-live="polite">Đang tải thông tin nâng cấp…</article>}
      {unit && stats && <article>
        <h3 data-upgrade-type={unit.code} data-category={unit.category}>{ENTITY_NAMES[unit.code] || unit.name} <UnitLevelStars level={level} />{next && level < MAX_UPGRADE_LEVEL ? <> → <UnitLevelStars level={level + 1} /></> : <small>CẤP TỐI ĐA</small>}</h3>
        <div className="upgrade-previews"><div><EntityIllustration code={unit.code} name={unit.name} category={unit.category} teamIndex={teamIndex} level={level}/><small><UnitLevelStars level={level} /> · {EQUIPMENT[level - 1]}</small></div>
          {next && level < MAX_UPGRADE_LEVEL && <div><EntityIllustration code={unit.code} name={unit.name} category={unit.category} teamIndex={teamIndex} level={level + 1}/><small><UnitLevelStars level={level + 1} /> · {EQUIPMENT[level]}</small></div>}</div>
        <dl>{([
          ["HP", stats.hp, next?.hp], ["Sát thương / đòn", stats.damage, next?.damage],
          ["Tốc độ bắn", stats.attack_rate_multiplier, next?.attack_rate_multiplier],
          ["Giây / đòn", stats.attack_interval_seconds, next?.attack_interval_seconds],
          ["Tầm bắn", stats.range, next?.range], ["Tốc độ di chuyển", stats.movement_speed, next?.movement_speed],
        ] as const).filter(([label, value]) => value !== null && (label !== "Tốc độ bắn" || stats.damage > 0)).map(([label, value, after]) => <div key={label}><dt>{label}</dt><dd>{formatUpgradeStat(label, value!)}{after != null ? ` → ${formatUpgradeStat(label, after)}` : ""}</dd></div>)}</dl>
        <p>Giá triển khai: {unit.cost} xu / đơn vị</p>
        {error && <p role="alert">{error}</p>}
      </article>}
      <footer className="team-upgrade-footer">
        <button disabled={pending} onClick={onClose}>Đóng</button>
        <div>        {!unlocked ? <p>Mở khóa công nghệ trước khi nâng cấp.</p> : !next || level >= MAX_UPGRADE_LEVEL ? <strong>CẤP TỐI ĐA</strong> : <>
          <p>Một lần thanh toán: <strong>{upgrade?.cost} xu</strong> · Nâng toàn bộ {ENTITY_NAMES[unit.code] || unit.name} lên <UnitLevelStars level={level + 1} />.</p>
          {confirming === signature ? <div className="upgrade-confirm"><button className="btn-secondary" disabled={pending} onClick={() => setConfirming(undefined)}>Hủy</button><button className="btn-primary" disabled={!canBuy} onClick={() => void buy()}>{pending ? "Đang nâng cấp…" : `Xác nhận · ${upgrade?.cost} xu`}</button></div>
            : <button className="btn-primary" disabled={!canBuy} onClick={() => setConfirming(signature)}>{coins < (upgrade?.cost ?? Infinity) ? "Không đủ xu" : "NÂNG CẤP TOÀN ĐỘI"}</button>}
        </>}
</div>
      </footer>
    </section>
  </div>;
}
