import { UnitType } from '../types/unit';

/** All boundaries use the catalog code sent to UPGRADE_TEAM_TYPE, never an instance ID.
 * Render entities and REST entities use different field names for the same code.
 */
export function resolveUpgradeType(entity: {
  team_id: string; unit_code?: string; unit_type_code?: string; unit_type_id?: string;
}, teamId: string | null, catalog: UnitType[]): string | null {
  if (!teamId || entity.team_id !== teamId) return null;
  const code = entity.unit_code ?? entity.unit_type_code;
  const type = catalog.find(u => code ? u.code === code : u.id === entity.unit_type_id);
  return type?.upgrade?.eligible ? type.code : null;
}
export interface UpgradeSelection {entityType?: string; sourceEntityId?: string;}
