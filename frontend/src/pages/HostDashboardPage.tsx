import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ExternalLink,
  FastForward,
  Pause,
  Play,
  RefreshCw,
  Shield,
  Square,
  Users,
  AlertTriangle,
  Award,
  DollarSign,
  Search,
  Filter,
  X,
  Clock,
  Ban,
  Sliders,
  Tv,
  Radio,
  FileText,
} from 'lucide-react';
import { api, getHostToken, getSavedHostSessions, setHostToken } from '../services/api';
import { Match } from '../types/match';
import { HostTelemetry, HostTeamTelemetry, MatchPreset, BalancePreview } from '../types/combat';
import { CombatDebugViewer } from '../components/game/CombatDebugViewer';
import './HostDashboardPage.css';

const formatTimer = (seconds: number) => {
  const safe = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(safe / 60).toString().padStart(2, '0')}:${(safe % 60).toString().padStart(2, '0')}`;
};

export const HostDashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [matches, setMatches] = useState<Match[]>([]);
  const [selectedMatch, setSelectedMatch] = useState<Match | null>(null);
  const [telemetry, setTelemetry] = useState<HostTelemetry | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Presets & Balance Preview State
  const [presets, setPresets] = useState<MatchPreset[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string>('standard_30m');
  const [balancePreview, setBalancePreview] = useState<BalancePreview | null>(null);
  const [showConfigModal, setShowConfigModal] = useState(false);

  // Events / Audit Log State
  const [events, setEvents] = useState<any[]>([]);
  const [eventFilter, setEventFilter] = useState<string>('ALL');
  const [eventSearch, setEventSearch] = useState<string>('');
  const [loadingEvents, setLoadingEvents] = useState<boolean>(false);

  // Administrative Override Modal State (2-step dangerous confirmations)
  const [activeModal, setActiveModal] = useState<
    'NONE' | 'CONFIRM_END' | 'OVERRIDE_PHASE' | 'ADJUST_COINS' | 'CLOSE_QUESTION' | 'KICK_MEMBER'
  >('NONE');
  const [selectedTeamForOverride, setSelectedTeamForOverride] = useState<HostTeamTelemetry | null>(null);
  const [targetPhase, setTargetPhase] = useState<string>('WAR');
  const [coinAmount, setCoinAmount] = useState<number>(50);
  const [overrideReason, setOverrideReason] = useState<string>('');
  const [endConfirmationText, setEndConfirmationText] = useState<string>('');
  const [selectedMemberId, setSelectedMemberId] = useState<string>('');

  const timerRef = useRef<any>(null);

  // 1. Initial Load
  useEffect(() => {
    loadMatches();
    loadPresets();
  }, []);

  const loadPresets = async () => {
    try {
      const data = await api.listPresets();
      setPresets(data);
    } catch {
      // Non-fatal fallback
    }
  };

  const loadMatches = async () => {
    try {
      const list = await api.listMatches();
      setMatches(list);
      if (list.length > 0 && !selectedMatch) {
        const saved = getSavedHostSessions();
        setSelectedMatch(saved.map((session) => list.find((match) => match.id === session.id)).find(Boolean) || list[0]);
      } else if (selectedMatch) {
        const updated = list.find((m) => m.id === selectedMatch.id);
        if (updated) setSelectedMatch(updated);
      }
    } catch {
      setMatches([]);
    }
  };

  // 2. Fetch Telemetry
  const fetchTelemetry = useCallback(async () => {
    if (!selectedMatch) return;
    try {
      const data = await api.getHostTelemetry(selectedMatch.id);
      const token = getHostToken(selectedMatch.id);
      if (token) setHostToken(token, selectedMatch);
      setTelemetry(data);
    } catch {
      // Telemetry might fail if match deleted
    }
  }, [selectedMatch]);

  // 3. Fetch Audit Events
  const fetchEvents = useCallback(async () => {
    if (!selectedMatch) return;
    setLoadingEvents(true);
    try {
      const params: any = { limit: 30, order: '-sequence_number' };
      if (eventFilter !== 'ALL') {
        params.event_type = eventFilter;
      }
      const data = await api.getEvents(selectedMatch.id, params);
      setEvents(data.events || []);
    } catch {
      setEvents([]);
    } finally {
      setLoadingEvents(false);
    }
  }, [selectedMatch, eventFilter]);

  // Polling loop for telemetry & events when active
  useEffect(() => {
    fetchTelemetry();
    fetchEvents();

    if (autoRefresh && selectedMatch) {
      timerRef.current = setInterval(() => {
        fetchTelemetry();
        fetchEvents();
      }, 3000);
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [selectedMatch, autoRefresh, fetchTelemetry, fetchEvents]);

  // Handle Preset Balance Preview
  const handleSelectPreset = (presetId: string) => {
    setSelectedPresetId(presetId);
    const p = presets.find((x) => x.id === presetId);
    if (p && selectedMatch) {
      api.previewConfig(selectedMatch.id, p.configuration).then(setBalancePreview).catch(() => {});
    }
  };

  const handleApplyPreset = async () => {
    if (!selectedMatch) return;
    setActionLoading(true);
    try {
      const updated = await api.applyPreset(selectedMatch.id, selectedPresetId);
      setSelectedMatch(updated);
      setShowConfigModal(false);
      loadMatches();
      fetchTelemetry();
      alert(`Đã áp dụng cấu hình Preset '${selectedPresetId}' thành công!`);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Áp dụng preset thất bại');
    } finally {
      setActionLoading(false);
    }
  };

  // Match Lifecycle Handlers
  const handleStart = async () => {
    if (!selectedMatch) return;
    setActionLoading(true);
    try {
      const res = await api.startMatch(selectedMatch.id);
      setSelectedMatch(res);
      loadMatches();
      fetchTelemetry();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Bắt đầu trận đấu thất bại');
    } finally {
      setActionLoading(false);
    }
  };

  const handlePause = async () => {
    if (!selectedMatch) return;
    setActionLoading(true);
    try {
      const res = await api.pauseMatch(selectedMatch.id);
      setSelectedMatch(res);
      loadMatches();
      fetchTelemetry();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Tạm dừng trận đấu thất bại');
    } finally {
      setActionLoading(false);
    }
  };

  const handleResume = async () => {
    if (!selectedMatch) return;
    setActionLoading(true);
    try {
      const res = await api.resumeMatch(selectedMatch.id);
      setSelectedMatch(res);
      loadMatches();
      fetchTelemetry();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Tiếp tục trận đấu thất bại');
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmEndMatch = async () => {
    if (!selectedMatch) return;
    if (endConfirmationText !== 'KET THUC') {
      alert('Vui lòng nhập chính xác "KET THUC" để xác nhận kết thúc trận đấu!');
      return;
    }
    setActionLoading(true);
    try {
      const res = await api.endMatch(selectedMatch.id);
      setSelectedMatch(res);
      setActiveModal('NONE');
      setEndConfirmationText('');
      loadMatches();
      fetchTelemetry();
      navigate(`/results/${selectedMatch.id}`);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Kết thúc trận đấu thất bại');
    } finally {
      setActionLoading(false);
    }
  };

  // Administrative Overrides Handlers (§14.8, §26, D15)
  const handleConfirmAdvancePhaseOverride = async () => {
    if (!selectedMatch) return;
    setActionLoading(true);
    try {
      const res = await api.advancePhaseOverride(
        selectedMatch.id,
        targetPhase,
        overrideReason || 'Host override: Skip phase'
      );
      setSelectedMatch(res);
      setActiveModal('NONE');
      setOverrideReason('');
      loadMatches();
      fetchTelemetry();
      fetchEvents();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Chuyển giai đoạn cưỡng chế thất bại');
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmAdjustCoins = async () => {
    if (!selectedMatch || !selectedTeamForOverride) return;
    setActionLoading(true);
    try {
      await api.overrideAdjustCoins(
        selectedMatch.id,
        selectedTeamForOverride.id,
        coinAmount,
        overrideReason || `Host override: Điều chỉnh ${coinAmount} coins`
      );
      setActiveModal('NONE');
      setOverrideReason('');
      fetchTelemetry();
      fetchEvents();
      alert(`Đã điều chỉnh ${coinAmount > 0 ? '+' : ''}${coinAmount} coins cho đội ${selectedTeamForOverride.name}!`);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Điều chỉnh coin thất bại');
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmCloseQuestion = async () => {
    if (!selectedMatch || !selectedTeamForOverride) return;
    setActionLoading(true);
    try {
      await api.overrideCloseQuestion(
        selectedMatch.id,
        selectedTeamForOverride.id,
        overrideReason || 'Host override: Đóng câu hỏi kẹt'
      );
      setActiveModal('NONE');
      setOverrideReason('');
      fetchTelemetry();
      fetchEvents();
      alert(`Đã đóng câu hỏi kẹt cho đội ${selectedTeamForOverride.name}!`);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Đóng câu hỏi thất bại');
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmKickMember = async () => {
    if (!selectedMatch || !selectedMemberId) return;
    setActionLoading(true);
    try {
      await api.removeMemberOverride(
        selectedMatch.id,
        selectedMemberId,
        overrideReason || 'Host override: Loại bỏ thành viên'
      );
      setActiveModal('NONE');
      setSelectedMemberId('');
      setOverrideReason('');
      fetchTelemetry();
      fetchEvents();
      alert('Đã loại bỏ thành viên khỏi trận đấu!');
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Loại bỏ thành viên thất bại');
    } finally {
      setActionLoading(false);
    }
  };

  const statusDisplay: Record<string, string> = {
    LOBBY: 'Sảnh chờ',
    ACTIVE: 'Đang diễn ra',
    PAUSED: 'Tạm dừng',
    FINISHED: 'Đã kết thúc',
  };

  const phaseDisplay: Record<string, string> = {
    LOBBY: 'Sảnh chờ',
    PREPARATION: 'Chuẩn bị (01)',
    BUILD_AND_SCOUT: 'Xây dựng & Do thám (02)',
    WAR: 'Chiến tranh khốc liệt (03)',
    FINAL_ASSAULT: 'Tổng công kích (04)',
    RESULTS: 'Kết quả chung cuộc',
  };

  const filteredEvents = events.filter((e) => {
    if (!eventSearch) return true;
    const str = JSON.stringify(e).toLowerCase();
    return str.includes(eventSearch.toLowerCase());
  });
  const continuousMatch = selectedMatch?.configuration.gameplay_mode === 'CONTINUOUS';
  const hostRound = telemetry?.current_round || selectedMatch?.configuration.current_round || 1;
  const hostTotalRounds = selectedMatch?.configuration.total_rounds || 3;
  const climaxSeconds = hostRound >= hostTotalRounds ? 30 : hostRound === 1 ? 15 : 20;
  const hostRemaining = telemetry?.phase_remaining_seconds ?? 0;
  const hostClock = formatTimer(hostRemaining);
  const hostPhaseLabel = continuousMatch
    ? selectedMatch?.phase === 'PREPARATION'
      ? hostRound === 1 ? 'Tập kết • chưa giao chiến' : `Tiếp tế • giao tranh tiếp diễn (Vòng ${hostRound})`
      : selectedMatch?.phase === 'WAR' ? hostRemaining <= climaxSeconds
        ? `CAO TRÀO • Vòng ${hostRound}/${hostTotalRounds}`
        : `Giao tranh • Vòng ${hostRound}/${hostTotalRounds}`
        : phaseDisplay[selectedMatch?.phase || ''] || selectedMatch?.phase || ''
    : phaseDisplay[selectedMatch?.phase || ''] || selectedMatch?.phase || '';
  const hostClockLabel = continuousMatch && selectedMatch?.phase === 'PREPARATION'
    ? `${hostRound === 1 ? 'Vòng 1 bắt đầu' : `Vòng ${hostRound} bắt đầu`} sau ${hostClock}`
    : continuousMatch && selectedMatch?.phase === 'WAR'
      ? hostRemaining <= climaxSeconds ? `Cao trào còn ${hostClock}` : `Cao trào sau ${formatTimer(hostRemaining - climaxSeconds)}`
      : `${telemetry?.phase_remaining_seconds ?? 0}s còn lại`;

  return (
    <div className="host-command">
      {/* 1. Header Banner & Host Lifecycle Bar */}
      <div
        className="glass-panel"
        data-host-panel="command"
        style={{
          padding: '24px 28px',
          marginBottom: '24px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '16px',
          borderLeft: '4px solid var(--accent-amber)',
        }}
      >
        <div className="host-command-title">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
            <span className="badge badge-amber" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Shield size={13} /> Bảng Điều Khiển Host (FR-09)
            </span>
            {selectedMatch && (
              <span className="badge badge-cyan">{statusDisplay[selectedMatch.status] || selectedMatch.status}</span>
            )}
            {selectedMatch && (
              <span className="badge badge-purple">{hostPhaseLabel}</span>
            )}
            {telemetry && (
              <span
                className="badge badge-emerald"
                style={{ display: 'flex', alignItems: 'center', gap: '4px', fontFamily: 'var(--font-mono)' }}
              >
                <Clock size={12} /> {hostClockLabel}
              </span>
            )}
          </div>
          <h1 style={{ fontSize: '1.85rem', fontWeight: 800, margin: 0 }}>
            {selectedMatch ? selectedMatch.name : 'Điều Hành Trận Đấu'}
            {selectedMatch && (
              <span style={{ fontSize: '1rem', color: 'var(--text-muted)', marginLeft: '10px', fontWeight: 500 }}>
                (Mã phòng: #{selectedMatch.room_code})
              </span>
            )}
          </h1>
        </div>

        {/* Action Controls Button Strip */}
        {selectedMatch && (
          <div className="host-lifecycle-actions" style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
            {selectedMatch.status === 'LOBBY' && (
              <>
                <button
                  id="btn-host-open-config"
                  onClick={() => setShowConfigModal(true)}
                  className="btn-secondary"
                  style={{ padding: '8px 14px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Sliders size={15} /> Cấu hình Preset
                </button>
                <button
                  id="btn-host-enter-lobby"
                  onClick={() => navigate(`/lobby/${selectedMatch.id}?host=1`)}
                  className="btn-secondary"
                  style={{ padding: '8px 14px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Users size={15} /> Vào sảnh chờ
                </button>
                <button
                  id="btn-host-start-match"
                  onClick={handleStart}
                  disabled={actionLoading}
                  className="btn-primary"
                  style={{ padding: '8px 16px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Play size={15} /> Bắt đầu trận
                </button>
              </>
            )}

            {selectedMatch.status === 'ACTIVE' && (
              <>
                <button
                  id="btn-host-pause-match"
                  onClick={handlePause}
                  disabled={actionLoading}
                  className="btn-secondary"
                  style={{ padding: '8px 14px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Pause size={15} /> Tạm dừng
                </button>
                <button
                  id="btn-host-advance-phase-override"
                  onClick={() => {
                    setTargetPhase(selectedMatch.configuration.gameplay_mode === 'CONTINUOUS'
                      ? selectedMatch.phase === 'PREPARATION' ? 'WAR'
                        : (selectedMatch.configuration.current_round || 1) >= (selectedMatch.configuration.total_rounds || 3) ? 'RESULTS' : 'PREPARATION'
                      : selectedMatch.phase === 'PREPARATION' ? 'BUILD_AND_SCOUT' : 'WAR');
                    setActiveModal('OVERRIDE_PHASE');
                  }}
                  disabled={actionLoading}
                  className="btn-secondary"
                  style={{ padding: '8px 14px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
                  title="Chuyển giai đoạn cưỡng chế (Admin Override)"
                >
                  <FastForward size={15} /> Chuyển giai đoạn
                </button>
              </>
            )}

            {selectedMatch.status === 'PAUSED' && (
              <button
                id="btn-host-resume-match"
                onClick={handleResume}
                disabled={actionLoading}
                className="btn-primary"
                style={{ padding: '8px 16px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Play size={15} /> Tiếp tục trận
              </button>
            )}

            {selectedMatch.status !== 'FINISHED' && (
              <button
                id="btn-host-end-match"
                onClick={() => {
                  setEndConfirmationText('');
                  setActiveModal('CONFIRM_END');
                }}
                disabled={actionLoading}
                className="btn-secondary"
                style={{
                  padding: '8px 14px',
                  fontSize: '0.85rem',
                  color: 'var(--accent-rose)',
                  borderColor: 'rgba(244, 63, 94, 0.4)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <Square size={14} /> Dừng trận sớm
              </button>
            )}

            {selectedMatch.status === 'FINISHED' && (
              <button
                id="btn-host-view-results"
                onClick={() => navigate(`/results/${selectedMatch.id}`)}
                className="btn-primary"
                style={{ padding: '8px 16px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Award size={15} /> Xem Kết Quả Chung Cuộc
              </button>
            )}

            <button
              id="btn-host-view-battlefield"
              onClick={() => navigate(`/battle/${selectedMatch.id}?host=1`)}
              className="btn-secondary"
              style={{ padding: '8px 12px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
              title="Quan sát chiến trường trực tiếp"
            >
              <Tv size={14} /> Chiến trường
            </button>

            <button
              onClick={() => {
                fetchTelemetry();
                fetchEvents();
              }}
              className="btn-secondary"
              style={{ padding: '8px 10px' }}
              title="Làm mới thông số ngay lập tức"
            >
              <RefreshCw size={14} />
            </button>
          </div>
        )}
      </div>

      {/* 2. Match Selector Strip */}
      {matches.length > 0 && (
        <div className="host-match-selector" style={{ marginBottom: '20px', display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '6px' }}>
          {matches.map((m) => (
            <button
              key={m.id}
              onClick={() => setSelectedMatch(m)}
              className={selectedMatch?.id === m.id ? 'btn-primary' : 'btn-secondary'}
              style={{ padding: '6px 14px', fontSize: '0.82rem', whiteSpace: 'nowrap' }}
            >
              {m.name} (#{m.room_code}) [{statusDisplay[m.status] || m.status}]
            </button>
          ))}
        </div>
      )}

      {selectedMatch ? (
        <div className="host-match-content" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* 3. Realtime Team Status & Telemetry Table (§14.8, §2.2) */}
          <div className="glass-panel host-panel host-telemetry-panel" style={{ padding: '24px' }}>
            <div
              className="host-panel-heading"
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '18px',
                flexWrap: 'wrap',
                gap: '12px',
              }}
            >
              <div>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Radio size={18} style={{ color: 'var(--accent-cyan)' }} />
                  Bảng Theo Dõi Thông Số Đội Hình Thời Gian Thực (Host Telemetry)
                </h3>
                <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                  Tự động đồng bộ mỗi 3 giây • Giám sát HP, Coins, Quân lực, Câu hỏi & Can thiệp sự cố
                </p>
              </div>

              <div className="host-telemetry-tools" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <label style={{ fontSize: '0.82rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={autoRefresh}
                    onChange={(e) => setAutoRefresh(e.target.checked)}
                  />
                  Tự động làm mới
                </label>
                <button
                  onClick={() => navigate(`/lobby/${selectedMatch.id}?host=1`)}
                  className="btn-secondary"
                  style={{ padding: '6px 12px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '4px' }}
                >
                  Phòng chờ <ExternalLink size={12} />
                </button>
              </div>
            </div>

            {telemetry && telemetry.teams.length > 0 ? (
              <div className="host-telemetry-scroll" style={{ overflowX: 'auto' }}>
                <table className="host-telemetry-table" style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-dim)', fontSize: '0.78rem', textTransform: 'uppercase' }}>
                      <th style={{ padding: '10px 12px' }}>ĐỘI HÌNH</th>
                      <th style={{ padding: '10px 12px' }}>CĂN CỨ & KHIÊN</th>
                      <th style={{ padding: '10px 12px' }}>KINH TẾ & ĐIỂM</th>
                      <th style={{ padding: '10px 12px' }}>QUÂN LỰC (UNITS / THÁP)</th>
                      <th style={{ padding: '10px 12px' }}>TIẾN ĐỘ CÂU HỎI</th>
                      <th style={{ padding: '10px 12px' }}>KẾT NỐI (MEMBERS)</th>
                      <th style={{ padding: '10px 12px', textAlign: 'center' }}>CAN THIỆP (OVERRIDE)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {telemetry.teams.map((t) => (
                      <tr key={t.id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                        {/* Team Name & Status */}
                        <td style={{ padding: '14px 12px' }}>
                          <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>{t.name}</div>
                          <div style={{ display: 'flex', gap: '6px', marginTop: '4px' }}>
                            <span className={t.status === 'ACTIVE' ? 'badge badge-cyan' : 'badge badge-rose'}>
                              {t.status === 'ACTIVE' ? 'Đang đấu' : 'Bị loại'}
                            </span>
                          </div>
                        </td>

                        {/* Base HP & Shield */}
                        <td style={{ padding: '14px 12px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span
                              style={{
                                color: t.base_hp < 400 ? 'var(--accent-rose)' : 'var(--text-main)',
                                fontFamily: 'var(--font-mono)',
                                fontWeight: 700,
                              }}
                            >
                              {t.base_hp} HP
                            </span>
                            {t.base_shield > 0 && (
                              <span className="badge badge-purple" style={{ fontSize: '0.7rem' }}>
                                +{t.base_shield} Khiên
                              </span>
                            )}
                          </div>
                          <div
                            style={{
                              width: '120px',
                              height: '6px',
                              background: 'rgba(255, 255, 255, 0.1)',
                              borderRadius: '3px',
                              overflow: 'hidden',
                              marginTop: '6px',
                            }}
                          >
                            <div
                              style={{
                                width: `${Math.min(100, (t.base_hp / 1000) * 100)}%`,
                                height: '100%',
                                background: t.base_hp < 300 ? 'var(--accent-rose)' : 'var(--accent-emerald)',
                              }}
                            />
                          </div>
                        </td>

                        {/* Coins & Score */}
                        <td style={{ padding: '14px 12px' }}>
                          <div style={{ color: 'var(--accent-amber)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
                            {t.coins} 🪙
                          </div>
                          <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: '2px' }}>
                            Điểm: <span style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>{t.score}</span>
                          </div>
                        </td>

                        {/* Units & Towers */}
                        <td style={{ padding: '14px 12px' }}>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <span className="badge badge-purple" title="Số quân lính Unit đang hoạt động">
                              ⚔️ {t.active_units} lính
                            </span>
                            <span className="badge badge-cyan" title="Số Tháp Tower đang hoạt động">
                              🛡️ {t.active_towers} tháp
                            </span>
                          </div>
                        </td>

                        {/* Questions & Pending Reward */}
                        <td style={{ padding: '14px 12px' }}>
                          <div style={{ fontSize: '0.85rem' }}>
                            Còn lại: <strong style={{ color: 'var(--text-main)' }}>{t.remaining_questions}</strong> câu
                          </div>
                          <div style={{ marginTop: '4px' }}>
                            {t.has_pending_reward ? (
                              <span className="badge badge-amber" style={{ animation: 'pulse 1.5s infinite' }}>
                                🎁 Chờ chọn thưởng
                              </span>
                            ) : t.current_question_status === 'PENDING_QUESTION' ? (
                              <span className="badge badge-cyan">Đang trả lời</span>
                            ) : (
                              <span className="badge badge-emerald">Chờ câu hỏi mới</span>
                            )}
                          </div>
                        </td>

                        {/* Members & Presence */}
                        <td style={{ padding: '14px 12px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span
                              style={{
                                width: '8px',
                                height: '8px',
                                borderRadius: '50%',
                                background: t.online_members_count > 0 ? '#10b981' : '#ef4444',
                              }}
                            />
                            <span style={{ fontWeight: 600 }}>
                              {t.online_members_count} / {t.members.length} online
                            </span>
                          </div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '4px' }}>
                            {t.members.map((m) => m.display_name).join(', ') || 'Chưa có thành viên'}
                          </div>
                        </td>

                        {/* Administrative Override Actions Button */}
                        <td style={{ padding: '14px 12px', textAlign: 'center' }}>
                          <div style={{ display: 'flex', gap: '6px', justifyContent: 'center' }}>
                            <button
                              onClick={() => {
                                setSelectedTeamForOverride(t);
                                setCoinAmount(50);
                                setActiveModal('ADJUST_COINS');
                              }}
                              className="btn-secondary"
                              style={{ padding: '6px 10px', fontSize: '0.78rem' }}
                              title="Điều chỉnh Coin đội hình"
                            >
                              <DollarSign size={13} /> Coin
                            </button>

                            {t.has_pending_reward && (
                              <button
                                onClick={() => {
                                  setSelectedTeamForOverride(t);
                                  setActiveModal('CLOSE_QUESTION');
                                }}
                                className="btn-secondary"
                                style={{ padding: '6px 10px', fontSize: '0.78rem', color: 'var(--accent-amber)' }}
                                title="Giải phóng câu hỏi / thưởng bị kẹt"
                              >
                                <AlertTriangle size={13} /> Gỡ kẹt
                              </button>
                            )}

                            {t.members.length > 0 && (
                              <button
                                onClick={() => {
                                  setSelectedTeamForOverride(t);
                                  setSelectedMemberId(t.members[0].id);
                                  setActiveModal('KICK_MEMBER');
                                }}
                                className="btn-secondary"
                                style={{ padding: '6px 10px', fontSize: '0.78rem', color: 'var(--accent-rose)' }}
                                title="Kick / Loại bỏ thành viên gặp sự cố"
                              >
                                <Ban size={13} /> Kick
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '36px', color: 'var(--text-dim)' }}>
                Chưa có dữ liệu đội hình. Vui lòng mở sảnh chờ để tạo các đội tham chiến.
              </div>
            )}
          </div>

          {/* 4. Match Event Audit Feed & Combat Log (§14.8, §26) */}
          <div className="glass-panel host-panel host-audit-panel" style={{ padding: '24px' }}>
            <div
              className="host-panel-heading host-audit-heading"
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px',
                flexWrap: 'wrap',
                gap: '12px',
              }}
            >
              <div>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <FileText size={18} style={{ color: 'var(--accent-purple)' }} />
                  Nhật Ký Tác Chiến & Kiểm Toán Sự Kiện (Match Audit Log)
                </h3>
                <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                  Ghi nhận đầy đủ biến động kinh tế, deploy lính, xây tháp, sát thương căn cứ và can thiệp Host (Bảo mật: Không lộ token)
                </p>
              </div>

              {/* Event Filter & Search */}
              <div className="host-event-tools" style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ position: 'relative' }}>
                  <Filter size={14} style={{ position: 'absolute', left: '10px', top: '10px', color: 'var(--text-muted)' }} />
                  <select
                    value={eventFilter}
                    onChange={(e) => setEventFilter(e.target.value)}
                    style={{
                      padding: '8px 12px 8px 30px',
                      background: 'rgba(0,0,0,0.3)',
                      color: 'var(--text-main)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '6px',
                      fontSize: '0.82rem',
                    }}
                  >
                    <option value="ALL">Tất cả sự kiện</option>
                    <option value="ADMINISTRATIVE_OVERRIDE">Chỉ can thiệp Host (Overrides)</option>
                    <option value="COMBAT_ROUND_RESOLVED">Chiến đấu (Combat Rounds)</option>
                    <option value="BASE_DESTROYED">Triệt hạ căn cứ</option>
                    <option value="QUESTION_ANSWERED">Trả lời câu hỏi</option>
                    <option value="REWARD_CLAIMED">Nhận phần thưởng</option>
                    <option value="UNIT_TRAINED">Thả quân (Deploy)</option>
                    <option value="TOWER_BUILT">Xây tháp phòng thủ</option>
                  </select>
                </div>

                <div style={{ position: 'relative' }}>
                  <Search size={14} style={{ position: 'absolute', left: '10px', top: '10px', color: 'var(--text-muted)' }} />
                  <input
                    type="text"
                    placeholder="Tìm kiếm nội dung..."
                    value={eventSearch}
                    onChange={(e) => setEventSearch(e.target.value)}
                    style={{
                      padding: '8px 12px 8px 30px',
                      background: 'rgba(0,0,0,0.3)',
                      color: 'var(--text-main)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '6px',
                      fontSize: '0.82rem',
                      width: '180px',
                    }}
                  />
                </div>

                <button
                  onClick={fetchEvents}
                  disabled={loadingEvents}
                  className="btn-secondary"
                  style={{ padding: '8px 12px', fontSize: '0.82rem' }}
                >
                  <RefreshCw size={13} />
                </button>
              </div>
            </div>

            {/* Event List */}
            <div
              className="host-event-list"
              style={{
                maxHeight: '320px',
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                paddingRight: '6px',
              }}
            >
              {filteredEvents.length > 0 ? (
                filteredEvents.map((ev) => (
                  <div
                    className="host-event-row"
                    key={ev.id || ev.sequence_number}
                    style={{
                      padding: '10px 14px',
                      background:
                        ev.event_type === 'ADMINISTRATIVE_OVERRIDE'
                          ? 'rgba(245, 158, 11, 0.1)'
                          : ev.event_type === 'BASE_DESTROYED'
                          ? 'rgba(244, 63, 94, 0.1)'
                          : 'rgba(255, 255, 255, 0.03)',
                      borderRadius: '6px',
                      borderLeft: `3px solid ${
                        ev.event_type === 'ADMINISTRATIVE_OVERRIDE'
                          ? 'var(--accent-amber)'
                          : ev.event_type === 'BASE_DESTROYED'
                          ? 'var(--accent-rose)'
                          : 'var(--border-subtle)'
                      }`,
                      fontSize: '0.82rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <div className="host-event-main">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span
                          style={{
                            fontFamily: 'var(--font-mono)',
                            color: 'var(--text-dim)',
                            fontWeight: 700,
                          }}
                        >
                          #{ev.sequence_number}
                        </span>
                        <span className="badge badge-purple" style={{ fontSize: '0.72rem' }}>
                          {ev.event_type}
                        </span>
                        <span style={{ color: 'var(--text-main)', fontWeight: 600 }}>
                          {ev.payload?.reason ||
                            ev.payload?.message ||
                            ev.payload?.action_type ||
                            (ev.event_type === 'COMBAT_ROUND_RESOLVED' ? `Lượt chiến đấu ${ev.payload?.round_number}` : '')}
                        </span>
                      </div>
                      {ev.payload && (
                        <div
                          style={{
                            color: 'var(--text-muted)',
                            fontSize: '0.75rem',
                            marginTop: '4px',
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          {JSON.stringify(ev.payload).slice(0, 140)}
                        </div>
                      )}
                    </div>

                    <div className="host-event-time" style={{ color: 'var(--text-dim)', fontSize: '0.72rem', whiteSpace: 'nowrap', marginLeft: '12px' }}>
                      {new Date(ev.created_at).toLocaleTimeString()}
                    </div>
                  </div>
                ))
              ) : (
                <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-dim)' }}>
                  Không có sự kiện nào phù hợp bộ lọc.
                </div>
              )}
            </div>
          </div>

          {/* Combat Engine Debug Controls (Phase 4 integration) */}
          {(selectedMatch.status === 'ACTIVE' || selectedMatch.status === 'PAUSED') && (
            <CombatDebugViewer
              matchId={selectedMatch.id}
              isHost={true}
              onRoundResolved={() => {
                fetchTelemetry();
                fetchEvents();
              }}
            />
          )}
        </div>
      ) : (
        <div className="glass-panel host-no-matches" style={{ padding: '48px', textAlign: 'center' }}>
          <Shield size={40} style={{ color: 'var(--text-dim)', margin: '0 auto 12px' }} />
          <h3>Không tìm thấy trận đấu nào</h3>
          <p style={{ color: 'var(--text-muted)', marginBottom: '20px' }}>
            Tạo trận đấu từ trang chủ để bắt đầu điều hành.
          </p>
          <button onClick={() => navigate('/')} className="btn-primary" style={{ padding: '10px 20px' }}>
            Về trang chủ
          </button>
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL 1: PRESET SELECTION & BALANCE PREVIEW (LOBBY ONLY) */}
      {/* ======================================================== */}
      {showConfigModal && (
        <div
          className="host-modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
        >
          <div className="glass-panel host-modal-card" style={{ maxWidth: '640px', width: '100%', padding: '28px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sliders size={20} style={{ color: 'var(--accent-cyan)' }} /> Cấu Hình Preset Trận Đấu
              </h3>
              <button
                onClick={() => setShowConfigModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', marginBottom: '18px' }}>
              Chọn preset phù hợp với thời lượng buổi team-building. Cấu hình chỉ có thể thay đổi khi trận ở trạng thái Sảnh chờ.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', marginBottom: '20px' }}>
              {presets.map((p) => (
                <div
                  key={p.id}
                  onClick={() => handleSelectPreset(p.id)}
                  style={{
                    padding: '14px',
                    borderRadius: '8px',
                    border: `2px solid ${selectedPresetId === p.id ? 'var(--accent-cyan)' : 'var(--border-subtle)'}`,
                    background: selectedPresetId === p.id ? 'rgba(56, 189, 248, 0.1)' : 'rgba(255,255,255,0.02)',
                    cursor: 'pointer',
                    textAlign: 'center',
                  }}
                >
                  <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>{p.name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '4px' }}>
                    {p.description}
                  </div>
                </div>
              ))}
            </div>

            {/* Balance Preview Card */}
            {balancePreview && (
              <div
                style={{
                  background: 'rgba(0,0,0,0.3)',
                  padding: '16px',
                  borderRadius: '8px',
                  marginBottom: '20px',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <h4 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--accent-amber)', marginBottom: '10px' }}>
                  📊 Xem Trước Cân Bằng (Balance Preview)
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px', fontSize: '0.82rem' }}>
                  <div>
                    Tổng thời lượng:{' '}
                    <strong>{balancePreview.total_match_minutes} phút</strong> ({balancePreview.estimated_combat_rounds} rounds)
                  </div>
                  <div>
                    Máu căn cứ mỗi đội: <strong>{balancePreview.initial_base_hp} HP</strong>
                  </div>
                  <div>
                    Nhịp độ trận đấu: <strong>{balancePreview.pacing}</strong>
                  </div>
                  <div>
                    Tổng Coin dự kiến:{' '}
                    <strong>{balancePreview.total_projected_coins_per_team} 🪙</strong>
                  </div>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button onClick={() => setShowConfigModal(false)} className="btn-secondary" style={{ padding: '8px 16px' }}>
                Hủy bỏ
              </button>
              <button
                onClick={handleApplyPreset}
                disabled={actionLoading}
                className="btn-primary"
                style={{ padding: '8px 20px' }}
              >
                {actionLoading ? 'Đang áp dụng...' : 'Áp Dụng Preset'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL 2: DANGEROUS END MATCH CONFIRMATION (2-STEP)       */}
      {/* ======================================================== */}
      {activeModal === 'CONFIRM_END' && (
        <div
          className="host-modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
        >
          <div className="glass-panel host-modal-card" style={{ maxWidth: '500px', width: '100%', padding: '28px', borderLeft: '4px solid var(--accent-rose)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px', color: 'var(--accent-rose)' }}>
              <AlertTriangle size={24} />
              <h3 style={{ fontSize: '1.25rem', fontWeight: 800, margin: 0 }}>Xác Nhận Dừng Trận Đấu Sớm</h3>
            </div>

            <p style={{ fontSize: '0.88rem', color: 'var(--text-main)', lineHeight: 1.5, marginBottom: '14px' }}>
              Hành động này sẽ <strong>kết thúc ngay lập tức</strong> trận đấu, chốt điểm số và tạo bản chụp kết quả (MatchResult snapshot) vĩnh viễn không thể hoàn tác (§14.9, FR-10).
            </p>

            <div style={{ marginBottom: '18px' }}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-dim)', display: 'block', marginBottom: '6px' }}>
                Vui lòng gõ chữ <strong style={{ color: 'var(--accent-rose)' }}>KET THUC</strong> để xác nhận:
              </label>
              <input
                type="text"
                value={endConfirmationText}
                onChange={(e) => setEndConfirmationText(e.target.value)}
                placeholder="KET THUC"
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  background: 'rgba(0,0,0,0.4)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  fontSize: '0.95rem',
                  fontWeight: 700,
                  letterSpacing: '1px',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button
                onClick={() => {
                  setActiveModal('NONE');
                  setEndConfirmationText('');
                }}
                className="btn-secondary"
                style={{ padding: '8px 16px' }}
              >
                Hủy
              </button>
              <button
                onClick={handleConfirmEndMatch}
                disabled={actionLoading || endConfirmationText !== 'KET THUC'}
                className="btn-primary"
                style={{
                  padding: '8px 20px',
                  background: endConfirmationText === 'KET THUC' ? 'var(--accent-rose)' : undefined,
                  borderColor: endConfirmationText === 'KET THUC' ? 'var(--accent-rose)' : undefined,
                }}
              >
                {actionLoading ? 'Đang kết thúc...' : 'Xác Nhận Dừng Trận'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL 3: ADVANCE PHASE OVERRIDE                          */}
      {/* ======================================================== */}
      {activeModal === 'OVERRIDE_PHASE' && (
        <div
          className="host-modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
        >
          <div className="glass-panel host-modal-card" style={{ maxWidth: '500px', width: '100%', padding: '28px', borderLeft: '4px solid var(--accent-amber)' }}>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 800, margin: '0 0 14px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FastForward size={20} style={{ color: 'var(--accent-amber)' }} /> Cưỡng Chế Chuyển Giai Đoạn (Override)
            </h3>

            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '16px' }}>
              Bỏ qua timer hiện tại và chuyển toàn bộ trận đấu sang giai đoạn tiếp theo. Thao tác này sẽ được ghi vào sổ kiểm toán (Audit Trail).
            </p>

            <div style={{ marginBottom: '14px' }}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-dim)', display: 'block', marginBottom: '6px' }}>
                Giai đoạn đích:
              </label>
              <select
                value={targetPhase}
                onChange={(e) => setTargetPhase(e.target.value)}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  background: 'rgba(0,0,0,0.4)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  fontSize: '0.9rem',
                }}
              >
                {selectedMatch?.configuration.gameplay_mode === 'CONTINUOUS' ? (
                  <option value={targetPhase}>{targetPhase === "WAR" ? "Giao tranh" : targetPhase === "PREPARATION" ? "Chuẩn bị vòng tiếp theo" : "Kết quả"}</option>
                ) : <>
                <option value="PREPARATION">Chuẩn bị (Preparation)</option>
                <option value="BUILD_AND_SCOUT">Xây dựng & Do thám (Build & Scout)</option>
                <option value="WAR">Chiến tranh khốc liệt (War)</option>
                <option value="FINAL_ASSAULT">Tổng công kích (Final Assault)</option>
                <option value="RESULTS">Kết quả chung cuộc (Results)</option>
                </>}
              </select>
            </div>

            <div style={{ marginBottom: '18px' }}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-dim)', display: 'block', marginBottom: '6px' }}>
                Lý do can thiệp (bắt buộc ghi nhận audit):
              </label>
              <input
                type="text"
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="Ví dụ: Host chuyển nhanh theo tiến độ sự kiện"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: 'rgba(0,0,0,0.4)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button onClick={() => setActiveModal('NONE')} className="btn-secondary" style={{ padding: '8px 16px' }}>
                Hủy
              </button>
              <button
                onClick={handleConfirmAdvancePhaseOverride}
                disabled={actionLoading}
                className="btn-primary"
                style={{ padding: '8px 20px' }}
              >
                {actionLoading ? 'Đang chuyển...' : 'Xác Nhận Chuyển'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL 4: ADJUST COINS OVERRIDE                          */}
      {/* ======================================================== */}
      {activeModal === 'ADJUST_COINS' && selectedTeamForOverride && (
        <div
          className="host-modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
        >
          <div className="glass-panel host-modal-card" style={{ maxWidth: '480px', width: '100%', padding: '28px' }}>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 800, margin: '0 0 14px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <DollarSign size={20} style={{ color: 'var(--accent-amber)' }} />
              Điều Chỉnh Coin — {selectedTeamForOverride.name}
            </h3>

            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '14px' }}>
              Số dư hiện tại: <strong style={{ color: 'var(--accent-amber)' }}>{selectedTeamForOverride.coins} 🪙</strong>.
              Thao tác này sẽ ghi nhận giao dịch ADMIN_OVERRIDE.
            </p>

            <div style={{ marginBottom: '14px' }}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-dim)', display: 'block', marginBottom: '6px' }}>
                Số lượng Coin thay đổi (+ thêm, - trừ bớt):
              </label>
              <input
                type="number"
                value={coinAmount}
                onChange={(e) => setCoinAmount(parseInt(e.target.value, 10) || 0)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: 'rgba(0,0,0,0.4)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  fontSize: '1rem',
                  fontFamily: 'var(--font-mono)',
                }}
              />
            </div>

            <div style={{ marginBottom: '18px' }}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-dim)', display: 'block', marginBottom: '6px' }}>
                Lý do điều chỉnh:
              </label>
              <input
                type="text"
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="Ví dụ: Bù lỗi hiển thị phần thưởng"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: 'rgba(0,0,0,0.4)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button onClick={() => setActiveModal('NONE')} className="btn-secondary" style={{ padding: '8px 16px' }}>
                Hủy
              </button>
              <button
                onClick={handleConfirmAdjustCoins}
                disabled={actionLoading || coinAmount === 0}
                className="btn-primary"
                style={{ padding: '8px 20px' }}
              >
                {actionLoading ? 'Đang thực hiện...' : 'Cập Nhật Coin'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL 5: CLOSE STUCK QUESTION OVERRIDE                   */}
      {/* ======================================================== */}
      {activeModal === 'CLOSE_QUESTION' && selectedTeamForOverride && (
        <div
          className="host-modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
        >
          <div className="glass-panel host-modal-card" style={{ maxWidth: '480px', width: '100%', padding: '28px', borderLeft: '4px solid var(--accent-amber)' }}>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 800, margin: '0 0 14px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <AlertTriangle size={20} style={{ color: 'var(--accent-amber)' }} />
              Đóng Câu Hỏi Kẹt — {selectedTeamForOverride.name}
            </h3>

            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '14px' }}>
              Đội này đang có câu hỏi hoặc phần thưởng chưa hoàn tất. Đóng câu hỏi cưỡng chế sẽ đánh dấu EXPIRED và cho phép đội nhận câu hỏi mới ngay lập tức.
            </p>

            <div style={{ marginBottom: '18px' }}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-dim)', display: 'block', marginBottom: '6px' }}>
                Lý do đóng câu hỏi:
              </label>
              <input
                type="text"
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="Ví dụ: Sự cố kết nối thí sinh"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: 'rgba(0,0,0,0.4)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button onClick={() => setActiveModal('NONE')} className="btn-secondary" style={{ padding: '8px 16px' }}>
                Hủy
              </button>
              <button
                onClick={handleConfirmCloseQuestion}
                disabled={actionLoading}
                className="btn-primary"
                style={{ padding: '8px 20px' }}
              >
                {actionLoading ? 'Đang đóng...' : 'Xác Nhận Đóng'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL 6: KICK / REASSIGN MEMBER OVERRIDE                */}
      {/* ======================================================== */}
      {activeModal === 'KICK_MEMBER' && selectedTeamForOverride && (
        <div
          className="host-modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
        >
          <div className="glass-panel host-modal-card" style={{ maxWidth: '480px', width: '100%', padding: '28px', borderLeft: '4px solid var(--accent-rose)' }}>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 800, margin: '0 0 14px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Ban size={20} style={{ color: 'var(--accent-rose)' }} />
              Loại Bỏ Thành Viên — {selectedTeamForOverride.name}
            </h3>

            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '14px' }}>
              Host có thể loại bỏ thí sinh bị mất kết nối vĩnh viễn hoặc vi phạm quy tắc mà không làm gián đoạn các đội còn lại (§17, D15).
            </p>

            <div style={{ marginBottom: '14px' }}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-dim)', display: 'block', marginBottom: '6px' }}>
                Chọn thành viên cần kick:
              </label>
              <select
                value={selectedMemberId}
                onChange={(e) => setSelectedMemberId(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: 'rgba(0,0,0,0.4)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                }}
              >
                {selectedTeamForOverride.members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.display_name} ({m.role})
                  </option>
                ))}
              </select>
            </div>

            <div style={{ marginBottom: '18px' }}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-dim)', display: 'block', marginBottom: '6px' }}>
                Lý do loại bỏ:
              </label>
              <input
                type="text"
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="Ví dụ: Rời cuộc chơi đột xuất"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: 'rgba(0,0,0,0.4)',
                  color: 'var(--text-main)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button onClick={() => setActiveModal('NONE')} className="btn-secondary" style={{ padding: '8px 16px' }}>
                Hủy
              </button>
              <button
                onClick={handleConfirmKickMember}
                disabled={actionLoading || !selectedMemberId}
                className="btn-primary"
                style={{
                  padding: '8px 20px',
                  background: 'var(--accent-rose)',
                  borderColor: 'var(--accent-rose)',
                }}
              >
                {actionLoading ? 'Đang thực hiện...' : 'Xác Nhận Kick'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
