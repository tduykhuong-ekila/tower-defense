import { useEffect, useRef, useState } from "react";
import { Coins, Gift, Unlock, Lock, CheckCircle, ArrowLeft, Loader2, Sparkles, X } from "lucide-react";
import { useModalFocus } from "./useModalFocus";
import { EntityIllustration } from "./game/EntityIllustration";
import { ENTITY_NAMES } from "../game/entityArtwork";
import { RewardClaim, RewardOptions, RewardType } from "../types/reward";

interface RewardSelectionModalProps {
  isOpen: boolean;
  rewardOptions: RewardOptions | null;
  unlockedCodes?: string[];
  matchEnded?: boolean;
  onClaimReward: (rewardType: RewardType, unitTypeId?: string, idempotencyKey?: string) => Promise<RewardClaim>;
  onClose: () => void;
  onSuccess: (claim: RewardClaim) => void;
  onRevealChange: (revealing: boolean) => void;
}

export function RewardSelectionModal({ isOpen, rewardOptions, unlockedCodes = [], matchEnded = false, onClaimReward, onClose, onSuccess, onRevealChange }: RewardSelectionModalProps) {
  const dialog = useRef<HTMLDivElement>(null);
  const processing = useRef(false);
  // A successful claim event clears live options before the HTTP response arrives.
  // Retain this bag while the server response and reveal finish.
  const optionsRef = useRef(rewardOptions);
  if (rewardOptions) optionsRef.current = rewardOptions;
  const options = rewardOptions || (processing.current ? optionsRef.current : null);
  const [viewMode, setViewMode] = useState<"CARDS" | "UNLOCK_GRID">("CARDS");
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [revealedClaim, setRevealedClaim] = useState<RewardClaim | null>(null);
  const [openingBag, setOpeningBag] = useState(false);
  const finishReveal = () => {
    if (!revealedClaim) return;
    processing.current = false;
    setIsProcessing(false);
    setRevealedClaim(null);
    onRevealChange(false);
    onClose();
  };
  useModalFocus(isOpen && !!options, dialog, () => {
    if (revealedClaim) finishReveal();
    else if (!processing.current) onClose();
  });
  useEffect(() => {
    if (!rewardOptions) return;
    processing.current = false;
    setIsProcessing(false);
    setErrorMsg(null);
    setSelectedUnitId(null);
    setViewMode("CARDS");
    setRevealedClaim(null);
    setOpeningBag(false);
  }, [rewardOptions?.team_question_id]);

  useEffect(() => {
    if (isOpen && viewMode === "UNLOCK_GRID") {
      dialog.current?.querySelector<HTMLButtonElement>(".unlock-card:not([disabled])")?.focus();
    }
  }, [viewMode, isOpen]);

  if (!isOpen || !options) return null;
  const { coin_amount, coin_distribution = [], unlock_available, message, eligible_units } = options;
  const mystery = coin_distribution.length > 0;
  const coinRange = mystery ? `${Math.min(...coin_distribution.map(item => item.amount))}–${Math.max(...coin_distribution.map(item => item.amount))}` : String(coin_amount);
  // Options only contain eligible locked entities; team events can invalidate a stale card.
  const eligible = eligible_units.filter(unit => !unlockedCodes.includes(unit.code));
  const selected = unlock_available ? eligible.find(unit => unit.code === selectedUnitId) : undefined;
  const canUnlock = unlock_available && eligible.length > 0;

  const claimReward = async (type: RewardType) => {
    if (matchEnded || processing.current || (type === "UNLOCK" && !selected)) return;
    processing.current = true;
    setIsProcessing(true);
    setErrorMsg(null);
    const revealBag = type === "COIN" && mystery;
    if (revealBag) {
      setOpeningBag(true);
      onRevealChange(true);
    }
    try {
      const key = crypto.randomUUID();
      const [claim] = await Promise.all([
        onClaimReward(type, type === "UNLOCK" ? selected!.code : undefined, key),
        revealBag ? new Promise(resolve => setTimeout(resolve, 250)) : Promise.resolve(),
      ]);
      if (revealBag && claim.reward_type === "COIN") {
        setOpeningBag(false);
        setRevealedClaim(claim);
        onSuccess(claim);
        return;
      }
      onSuccess(claim);
      onRevealChange(false);
      onClose();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Không thể nhận phần thưởng. Vui lòng thử lại.");
      processing.current = false;
      setIsProcessing(false);
      setOpeningBag(false);
      onRevealChange(false);
    }
  };

  return <div className="reward-overlay" ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="reward-title">
    <div className={`reward-dialog fantasy-frame ${viewMode === "UNLOCK_GRID" ? "show-unlocks" : ""}`} aria-busy={isProcessing && !revealedClaim}>
      <header className="reward-header">
        <Sparkles size={28} aria-hidden="true" />
        <div><h2 id="reward-title">{revealedClaim ? "PHẦN THƯỞNG CỦA ĐỘI" : viewMode === "CARDS" ? "LỰA CHỌN PHẦN THƯỞNG CHIẾN THẮNG" : "CHỌN PHẦN THƯỞNG MỞ KHÓA"}</h2>
          <p>{revealedClaim ? "Coin đã được cộng vào ngân sách chung của đội." : "Đội của bạn vừa trả lời chính xác. Chọn duy nhất 1 phần thưởng."}</p></div>
        <button className="reward-close" aria-label="Đóng phần thưởng" disabled={isProcessing && !revealedClaim} onClick={revealedClaim ? finishReveal : onClose}><X size={20} /></button>
      </header>
      {matchEnded && <p role="status" className="reward-error">Trận đấu đã kết thúc. Không thể nhận thêm phần thưởng. Đóng cửa sổ để xem kết quả.</p>}
      {errorMsg && <p className="reward-error" role="alert">{errorMsg}</p>}
      {openingBag ? <div className="coin-bag-opening reward-scroll" role="status" aria-live="polite">
        <Gift size={72} aria-hidden="true" /><h3>Đang mở túi coin...</h3><p>Phần thưởng bất ngờ đang chờ đội bạn!</p>
      </div> : revealedClaim ? <div className={`coin-bag-reveal reward-scroll ${revealedClaim.coin_amount === 60 ? "jackpot" : ""}`} role="status" aria-live="polite">
        <Sparkles size={56} aria-hidden="true" />
        <h3>{revealedClaim.coin_amount === 60 ? "May mắn!" : revealedClaim.coin_amount === 40 ? "Phần thưởng bất ngờ!" : "Đội bạn nhận được"}</h3>
        <strong className="coin-bag-amount">+{revealedClaim.coin_amount} coin</strong>
        <p>Đã cộng vào ngân sách của đội.</p>
        <button className="gold-button" onClick={finishReveal}>Tiếp tục</button>
      </div> : viewMode === "CARDS" ? <div className="reward-options reward-scroll">
        <section className="reward-option coin-option">
          {mystery ? <Gift size={36} aria-hidden="true" /> : <Coins size={36} aria-hidden="true" />}<small>LỰA CHỌN A</small><h3>{mystery ? "Túi coin bí ẩn" : `+${coin_amount} xu tăng viện`}</h3>
          <p>{mystery ? <>Mở túi để nhận <strong>{coinRange} coin ngẫu nhiên</strong> cho cả đội. Số coin sẽ được tiết lộ khi mở túi.</> : <>Cộng ngay <strong>+{coin_amount} xu</strong> vào ngân sách của đội để xuất quân, xây tháp hoặc gia cố căn cứ.</>}</p>
          {mystery && <details className="coin-bag-odds"><summary>Xem tỷ lệ nhận coin</summary><table><caption>Xác suất mỗi lần mở túi</caption><thead><tr><th>Coin</th><th>Tỷ lệ</th></tr></thead><tbody>{coin_distribution.map(item => <tr key={item.amount}><td>{item.amount}</td><td>{item.probability_percent}%</td></tr>)}</tbody></table></details>}
          <button className="gold-button" disabled={isProcessing || matchEnded} onClick={() => claimReward("COIN")}>
            {isProcessing ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle size={18} />} {mystery ? `Mở túi coin · ${coinRange}` : `Nhận +${coin_amount} xu`}
          </button>
        </section>
        <section className="reward-option">
          {canUnlock ? <Unlock size={36} aria-hidden="true" /> : <Lock size={36} aria-hidden="true" />}<small>LỰA CHỌN B</small><h3>Mở khóa công nghệ</h3>
          <p>{canUnlock ? `Mở khóa miễn phí 1 đơn vị hoặc công sự (${eligible.length} lựa chọn). Cả đội có thể triển khai đến hết trận đấu.` : message || "Toàn bộ đơn vị đã được mở khóa. Hãy nhận xu để tiếp tục tăng cường căn cứ."}</p>
          <button className="btn-primary" disabled={!canUnlock || isProcessing} onClick={() => setViewMode("UNLOCK_GRID")}><Unlock size={18} /> Chọn Đơn Vị Mở Khóa ({eligible.length})</button>
        </section>
      </div> : <>
        <div className="reward-scroll unlock-grid-scroll">
          <div className="unlock-intro"><button className="btn-secondary" disabled={isProcessing} onClick={() => setViewMode("CARDS")}><ArrowLeft size={16} /> Quay lại</button>
            <p>Chọn 1 đơn vị hoặc công sự để mở khóa cho cả đội trong trận này.</p></div>
          <div className="unlock-grid" role="group" aria-label="Đơn vị có thể mở khóa">
            {eligible_units.map(unit => {
              const unlocked = unlockedCodes.includes(unit.code);
              const isSelected = selected?.code === unit.code;
              const name = ENTITY_NAMES[unit.code] || unit.name;
              return <button type="button" key={unit.id} className={`unlock-card ${isSelected ? "selected" : ""}`}
                aria-pressed={isSelected} disabled={isProcessing || unlocked || !unlock_available} onClick={() => setSelectedUnitId(unit.code)}>
                <EntityIllustration code={unit.code} name={name} category={unit.category} />
                <span className="unlock-card-heading"><strong>{name}</strong>{isSelected && <CheckCircle size={20} aria-hidden="true" />}</span>
                <span className="unlock-kind">{unit.category === "TOWER" ? "CÔNG SỰ PHÒNG THỦ" : "QUÂN CHIẾN ĐẤU"}</span>
                <span className="unlock-description">{unit.description}</span>
                <span className="unlock-stats"><span>HP <b>{unit.hp}</b></span><span>Sát thương <b>{unit.damage}</b></span><span>Tầm <b>{unit.range} node</b></span>
                  {unit.category === "UNIT" && unit.movement_speed !== undefined && <span>Tốc độ <b>{unit.movement_speed}</b></span>}</span>
                <span className="unlock-card-bottom"><span>{unit.category === "TOWER" ? "Giá xây" : "Giá triển khai"}: <b>{unit.cost} xu</b></span>
                  <span>{unlocked ? "Đã mở khóa" : isSelected ? "Đã chọn" : "Đang khóa"}</span></span>
              </button>;
            })}
          </div>
        </div>
        <footer className="unlock-footer">
          <span role="status">{selected ? `Đã chọn: ${ENTITY_NAMES[selected.code] || selected.name}` : "Chọn một thẻ để tiếp tục"}</span>
          <button className="btn-secondary" disabled={isProcessing} onClick={() => setViewMode("CARDS")}>Hủy</button>
          <button className="gold-button" disabled={!selected || isProcessing || matchEnded} onClick={() => claimReward("UNLOCK")}>
            {isProcessing ? <><Loader2 size={18} className="animate-spin" /> Đang mở khóa...</> : <><Unlock size={18} /> Xác Nhận Mở Khóa Đơn Vị</>}
          </button>
        </footer>
      </>}
    </div>
  </div>;
}
