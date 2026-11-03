import { UnitSimulationState } from "../types/unit";

export function towerSalePrice(entity: {current_hp: number; max_hp: number; simulation_state?: UnitSimulationState}, fallbackCost = 0): number {
  return Math.floor(Math.max(0, entity.simulation_state?.build_cost ?? fallbackCost)
    * Math.max(0, Math.min(entity.current_hp, entity.max_hp)) / Math.max(1, entity.max_hp));
}
