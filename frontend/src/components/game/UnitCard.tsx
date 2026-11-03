import { UnitLevelStars } from "./UnitLevelStars";
import { EntityIllustration } from "./EntityIllustration";
import React from 'react';
import {
  Swords,
  Crosshair,
  Lock,
  Unlock,
  Coins,
  Activity,
} from 'lucide-react';
import { CardVisualStatus, UnitType } from '../../types/unit';

interface UnitCardProps {
  unit: UnitType;
  status: CardVisualStatus;
  userCoins?: number;
  deployedCount?: number;
  onDeploy?: (unit: UnitType) => void;
  isLoading?: boolean;
}

export const UnitCard: React.FC<UnitCardProps> = ({
  unit,
  status,
  deployedCount = 0,
  onDeploy,
  isLoading = false,
}) => {
  const getStatusBadge = () => {
    switch (status) {
      case 'LOCKED':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '999px',
              fontSize: '0.7rem',
              fontWeight: 700,
              background: 'rgba(239, 68, 68, 0.15)',
              color: '#f87171',
              border: '1px solid rgba(239, 68, 68, 0.3)',
            }}
          >
            <Lock size={10} /> Khóa
          </span>
        );
      case 'AVAILABLE_TO_UNLOCK':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '999px',
              fontSize: '0.7rem',
              fontWeight: 700,
              background: 'rgba(56, 189, 248, 0.2)',
              color: 'var(--accent-cyan)',
              border: '1px solid rgba(56, 189, 248, 0.4)',
              boxShadow: '0 0 10px rgba(56, 189, 248, 0.2)',
            }}
          >
            <Unlock size={10} /> Có thể mở khóa
          </span>
        );
      case 'UNLOCKED_AFFORDABLE':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '999px',
              fontSize: '0.7rem',
              fontWeight: 700,
              background: 'rgba(16, 185, 129, 0.15)',
              color: 'var(--accent-emerald)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
            }}
          >
            Sẵn sàng
          </span>
        );
      case 'UNLOCKED_UNAFFORDABLE':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '999px',
              fontSize: '0.7rem',
              fontWeight: 700,
              background: 'rgba(245, 158, 11, 0.15)',
              color: 'var(--accent-amber)',
              border: '1px solid rgba(245, 158, 11, 0.3)',
            }}
          >
            Thiếu Coin
          </span>
        );
      case 'DEPLOYED':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '999px',
              fontSize: '0.7rem',
              fontWeight: 700,
              background: 'rgba(139, 92, 246, 0.2)',
              color: '#c084fc',
              border: '1px solid rgba(139, 92, 246, 0.4)',
            }}
          >
            Đang chiến đấu ({deployedCount})
          </span>
        );
      case 'DESTROYED':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '999px',
              fontSize: '0.7rem',
              fontWeight: 700,
              background: 'rgba(148, 163, 184, 0.2)',
              color: 'var(--text-muted)',
              border: '1px solid rgba(148, 163, 184, 0.3)',
            }}
          >
            Bị tiêu diệt
          </span>
        );
    }
  };

  const isLocked = status === 'LOCKED';
  const isAffordable = status === 'UNLOCKED_AFFORDABLE';

  return (
    <div
      style={{
        background: isLocked
          ? 'rgba(15, 23, 42, 0.4)'
          : isAffordable
          ? 'linear-gradient(145deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%)'
          : 'rgba(15, 23, 42, 0.6)',
        border: isAffordable
          ? '1px solid rgba(56, 189, 248, 0.4)'
          : isLocked
          ? '1px dashed rgba(255, 255, 255, 0.1)'
          : '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '10px',
        padding: '14px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        boxShadow: isAffordable
          ? '0 4px 20px rgba(0, 0, 0, 0.4), 0 0 15px rgba(56, 189, 248, 0.08)'
          : '0 4px 15px rgba(0, 0, 0, 0.3)',
        transition: 'all 0.2s ease',
        opacity: isLocked ? 0.65 : 1,
      }}
    >
      <EntityIllustration code={unit.code} name={unit.name} category={unit.category} level={unit.level ?? 1} />
      <UnitLevelStars level={unit.level} />
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
            <span style={{ fontWeight: 700, fontSize: '0.95rem', color: isLocked ? 'var(--text-muted)' : '#ffffff' }}>
              {unit.name}
            </span>
          </div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>
            {unit.code.toUpperCase()}
          </div>
        </div>
        {getStatusBadge()}
      </div>

      {/* Description */}
      <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0, lineHeight: 1.4 }}>
        {unit.description}
      </p>

      {/* Stats row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '6px',
          background: 'rgba(0, 0, 0, 0.25)',
          padding: '8px',
          borderRadius: '6px',
          border: '1px solid rgba(255, 255, 255, 0.04)',
        }}
      >
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '3px' }}>
            <Activity size={10} style={{ color: 'var(--accent-rose)' }} /> HP
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.85rem', color: '#ffffff' }}>
            {unit.hp}
          </div>
        </div>

        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '3px' }}>
            <Swords size={10} style={{ color: 'var(--accent-amber)' }} /> Công
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.85rem', color: '#ffffff' }}>
            {unit.damage}
          </div>
        </div>

        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '3px' }}>
            <Crosshair size={10} style={{ color: 'var(--accent-cyan)' }} /> Tầm
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.85rem', color: '#ffffff' }}>
            {unit.range} node
          </div>
        </div>
      </div>

      {/* Action and Cost Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto', paddingTop: '6px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Coins size={14} style={{ color: 'var(--accent-amber)' }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.95rem', color: 'var(--accent-amber)' }}>
            {unit.cost}
          </span>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Coin</span>
        </div>

        {isLocked ? (
          <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Lock size={12} /> Cần trả lời đúng
          </div>
        ) : (
          <button
            disabled={!isAffordable || isLoading}
            onClick={() => onDeploy && onDeploy(unit)}
            className="btn-primary"
            style={{
              padding: '6px 14px',
              fontSize: '0.8rem',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              background: isAffordable
                ? 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)'
                : 'rgba(255, 255, 255, 0.08)',
              cursor: isAffordable && !isLoading ? 'pointer' : 'not-allowed',
              opacity: isAffordable ? 1 : 0.6,
            }}
          >
            <Swords size={12} />
            {isLoading ? 'Đang gửi...' : isAffordable ? 'Xuất Quân' : 'Thiếu Coin'}
          </button>
        )}
      </div>
    </div>
  );
};
