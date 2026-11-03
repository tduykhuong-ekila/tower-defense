import { Coins, Lock } from "lucide-react";
import { ENTITY_NAMES, entityArtwork } from "../../game/entityArtwork";
import { UnitType } from "../../types/unit";
import { UnitLevelStars } from "./UnitLevelStars";

export interface GameItemCardContentProps {
  unit: UnitType;
  teamIndex: number;
  unlocked: boolean;
}

/** Shared fixed rows for the army and fortification pickers. Stats stay in the hover card. */
export function GameItemCardContent({ unit, teamIndex, unlocked }: GameItemCardContentProps) {
  return <>
    <span className="game-item-card__artwork">
      <img src={entityArtwork(unit.code, teamIndex, unit.level ?? 1)} alt="" />
    </span>
    <span className="game-item-card__stars"><UnitLevelStars level={unit.level} size="compact" /></span>
    <strong className="game-item-card__name">{ENTITY_NAMES[unit.code] || unit.name}</strong>
    <span className="card-cost">
      {unlocked ? <><Coins size={13} aria-hidden="true" />{unit.cost}</> : <><Lock size={12} aria-hidden="true" />Mở khóa</>}
    </span>
  </>;
}
