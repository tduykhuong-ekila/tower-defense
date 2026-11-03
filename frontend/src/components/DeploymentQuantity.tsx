interface Props {
  value: string;
  maximum: number;
  cost: number;
  coins: number;
  disabled: boolean;
  reason?: string;
  onChange: (value: string) => void;
}

export function DeploymentQuantity({value, maximum, cost, coins, disabled, reason, onChange}: Props) {
  const quantity = Number(value);
  const valid = Number.isSafeInteger(quantity) && quantity >= 1;
  return <div className="quantity-panel" aria-label="Số lượng triển khai">
    <div className="quantity-heading"><strong>Số lượng</strong><small>{cost} xu / đơn vị</small></div>
    <div className="quantity-stepper">
      <button aria-label="Giảm số lượng" disabled={disabled || !valid || quantity <= 1}
        onClick={() => onChange(String(quantity - 1))}>−</button>
      <input aria-label="Số lượng quân" type="number" min="1" step="1" max={maximum || undefined}
        value={value} disabled={disabled} aria-invalid={!valid || (valid && quantity > maximum)}
        onChange={event => onChange(event.target.value)} />
      <button aria-label="Tăng số lượng" disabled={disabled || !valid || quantity >= maximum}
        onClick={() => onChange(String(quantity + 1))}>+</button>
    </div>
    <div className="quantity-total" aria-live="polite"><strong>Tổng: {valid ? cost * quantity : "—"} xu</strong><span>Hiện có: {coins} xu · Tối đa: {maximum}</span></div>
    {reason && <p className="quantity-error" role="status">{reason}</p>}
  </div>;
}
