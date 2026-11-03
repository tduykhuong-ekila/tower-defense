import { UnitLevelStars } from "./UnitLevelStars";
import { MAX_UPGRADE_LEVEL } from "../../game/upgradeLevel";
import { EntityIllustration } from "./EntityIllustration";
import { Shield, Zap, ArrowUpCircle, Heart } from 'lucide-react';
import { GameEntity } from '../../types/unit';

interface TowerCardProps {
  entity: GameEntity;
  userCoins: number;
  upgradeCost?: number;
  onUpgrade?: (entity: GameEntity) => void;
  isUpgrading?: boolean;
}

export const TowerCard: React.FC<TowerCardProps> = ({
  entity,
  userCoins,
  upgradeCost,
  onUpgrade,
  isUpgrading = false,
}) => {
  const isLevelMax = entity.level >= MAX_UPGRADE_LEVEL;
  const canAffordUpgrade = upgradeCost !== undefined && userCoins >= upgradeCost && !isLevelMax && !!onUpgrade;
  const isDisabled = entity.status === 'DISABLED';

  return (
    <div
      style={{
        background: isDisabled
          ? 'rgba(239, 68, 68, 0.08)'
          : 'linear-gradient(145deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.8) 100%)',
        border: isDisabled
          ? '1px solid rgba(239, 68, 68, 0.4)'
          : entity.level >= 2
          ? '1px solid var(--accent-amber)'
          : '1px solid var(--border-subtle)',
        borderRadius: '10px',
        padding: '12px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        boxShadow: entity.level >= 2 ? '0 0 15px rgba(245, 158, 11, 0.15)' : 'none',
      }}
    >
      <EntityIllustration code={entity.unit_type_code} name={entity.name} category={entity.entity_kind} level={entity.level} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: '0.9rem', color: '#ffffff' }}>
            {entity.name}
          </div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
            Vị trí: <strong>{entity.current_node_id}</strong>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {isDisabled && (
            <span
              style={{
                fontSize: '0.7rem',
                fontWeight: 700,
                color: '#f87171',
                background: 'rgba(239, 68, 68, 0.2)',
                padding: '2px 6px',
                borderRadius: '4px',
                display: 'flex',
                alignItems: 'center',
                gap: '3px',
              }}
            >
              <Zap size={10} /> EMP Vô hiệu
            </span>
          )}
          <UnitLevelStars level={entity.level} />
        </div>
      </div>

      {/* Stats row */}
      <div
        style={{
          display: 'flex',
          gap: '12px',
          background: 'rgba(0, 0, 0, 0.2)',
          padding: '6px 10px',
          borderRadius: '6px',
          fontSize: '0.75rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--accent-rose)' }}>
          <Heart size={12} /> {entity.current_hp}/{entity.max_hp}
        </div>
        {entity.current_shield > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--accent-cyan)' }}>
            <Shield size={12} /> +{entity.current_shield} Khiên
          </div>
        )}
        {(entity.damage ?? 0) > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--accent-amber)', fontWeight: 600 }}>
            Sát thương: {entity.damage ?? "—"}
          </div>
        )}
      </div>

      {isLevelMax && <strong>CẤP TỐI ĐA</strong>}
      {/* Upgrade Action */}
      {!isLevelMax && (
        <button
          disabled={!canAffordUpgrade || isUpgrading || isDisabled}
          onClick={() => onUpgrade && onUpgrade(entity)}
          className="btn-secondary"
          style={{
            marginTop: '2px',
            padding: '5px 10px',
            fontSize: '0.75rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            background: canAffordUpgrade ? 'rgba(245, 158, 11, 0.15)' : 'rgba(255, 255, 255, 0.05)',
            border: canAffordUpgrade ? '1px solid rgba(245, 158, 11, 0.3)' : undefined,
            color: canAffordUpgrade ? 'var(--accent-amber)' : 'var(--text-dim)',
            cursor: canAffordUpgrade && !isUpgrading ? 'pointer' : 'not-allowed',
          }}
        >
          <ArrowUpCircle size={13} />
          {isUpgrading ? 'Đang nâng cấp...' : <>Nâng cấp toàn đội <UnitLevelStars level={entity.level + 1} /> ({upgradeCost ?? "—"} Coin)</>}
        </button>
      )}
    </div>
  );
};
