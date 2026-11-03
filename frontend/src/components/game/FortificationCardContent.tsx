import { GameItemCardContent, GameItemCardContentProps } from "./GameItemCardContent";

/** Stable picker content; full stats and rank names live in EntityInfoCard. */
export function FortificationCardContent(props: GameItemCardContentProps) {
  return <GameItemCardContent {...props} />;
}
