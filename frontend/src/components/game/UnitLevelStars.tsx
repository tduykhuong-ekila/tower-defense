import { Star } from "lucide-react";
import { upgradeLevel } from "../../game/upgradeLevel";
import "./unitLevelStars.css";

export interface UnitLevelStarsProps {
  level?: number;
  size?: "tiny" | "compact" | "normal" | "large";
}

/** Upgrade level only; affordability, unlock and selection have separate states. */
export function UnitLevelStars({ level = 1, size = "normal" }: UnitLevelStarsProps) {
  const count = upgradeLevel(level);
  return <span className={`unit-level-stars unit-level-stars--${size}`} role="img"
    aria-label={`Cấp ${count} trên 3`} data-level={count}>
    {Array.from({ length: count }, (_, index) =>
      <Star key={index} aria-hidden="true" fill="currentColor" strokeWidth={1.5} />)}
  </span>;
}
