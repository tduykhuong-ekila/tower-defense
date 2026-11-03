import { PALETTE, teamLabel } from "../game/map";
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import {
  AlertCircle,
  CheckCircle2,
  Copy,
  Crown,
  Lock,
  Play,
  Plus,
  RefreshCw,
  Settings,
  Shield,
  Trash2,
  Unlock,
  UserMinus,
  Users,
  X,
} from 'lucide-react';
import {
  api,
  getActiveMember,
  isHostMode,
  setActiveMember,
} from '../services/api';
import { Match, ParticipantRole, Team, TeamMember } from '../types/match';
import { wsClient } from '../services/websocket';
import { ServerEnvelope } from '../types/realtime';
import { MaximumTeamsSelect, useRoomConstraints } from '../components/MaximumTeamsSelect';
import { activeMemberCount, teamHasPlayers } from '../game/teamMembership';
import { teamInvitationUrl, teamJoinIssue } from '../game/teamJoining';
import { useModalFocus } from '../components/useModalFocus';
import './LobbyPage.css';

export const LobbyPage: React.FC = () => {
  const { matchId: paramId, roomCode: paramCode } = useParams<{ matchId?: string; roomCode?: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  const [match, setMatch] = useState<Match | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [inviteTeam, setInviteTeam] = useState<Team | null>(null);
  const [inviteCopied, setInviteCopied] = useState(false);
  const [inviteError, setInviteError] = useState('');
  const inviteDialogRef = useRef<HTMLDivElement>(null);
  useModalFocus(!!inviteTeam, inviteDialogRef, () => setInviteTeam(null));
  const [isHost, setIsHost] = useState(false);

  // Active member if participant
  const [activeMember, setActiveMemberState] = useState<TeamMember | null>(null);

  // Modals & Forms
  const [showAddTeamModal, setShowAddTeamModal] = useState(false);
  const [newTeamName, setNewTeamName] = useState('');
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [editHp, setEditHp] = useState(500);
  const [editCoins, setEditCoins] = useState(100);
  const { constraints, error: constraintsError } = useRoomConstraints();
  const [editMaxTeams, setEditMaxTeams] = useState<number>();
  const [actionLoading, setActionLoading] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);

  const isPollingRef = useRef(true);

  // Only an explicit Host URL enters Host mode; stored credentials alone never do.
  useEffect(() => {
    setIsHost(isHostMode());

    const storedMember = getActiveMember();
    setActiveMemberState(storedMember);
  }, [location.search]);

  // Load match data
  const fetchMatch = useCallback(async (isInitial = false) => {
    if (isInitial) setLoading(true);
    const target = paramId || paramCode;
    if (!target) {
      setError('Không có ID hoặc Mã phòng đấu.');
      setLoading(false);
      return;
    }

    try {
      let data: Match;
      // UUID has dashes and 36 chars; 6 chars is room code
      if (target.length === 6) {
        data = await api.getMatchByCode(target);
      } else {
        data = await api.getMatch(target);
      }

      setMatch(data);
      setError(null);

      // Host assignments update the server member record; keep the participant
      // session in sync so BattlePage does not treat an assigned player as a spectator.
      const storedMember = getActiveMember();
      if (storedMember) {
        const refreshedMember = data.all_members?.find(
          (member) => member.id === storedMember.id,
        );
        if (refreshedMember) {
          setActiveMember(refreshedMember);
          setActiveMemberState(refreshedMember);
        }
      }

      // If match has already started and is in PREPARATION or later, auto-navigate
      if (data.status === 'ACTIVE' && data.phase !== 'LOBBY') {
        isPollingRef.current = false;
        navigate(`/battle/${data.id}${isHostMode() ? '?host=1' : ''}`);
      }
    } catch (err: unknown) {
      if (isInitial) {
        setError(err instanceof Error ? err.message : 'Không thể tải thông tin phòng đấu');
      }
    } finally {
      if (isInitial) setLoading(false);
    }
  }, [paramId, paramCode, navigate]);

  // Initial fetch and 2-second polling loop (§14.3)
  useEffect(() => {
    isPollingRef.current = true;
    fetchMatch(true);

    const interval = setInterval(() => {
      if (isPollingRef.current) {
        fetchMatch(false);
      }
    }, 2000);

    return () => {
      isPollingRef.current = false;
      clearInterval(interval);
    };
  }, [fetchMatch]);

  // WebSocket realtime synchronization
  useEffect(() => {
    if (!match?.id) return;

    wsClient.connect(match.id);

    const unsubStatus = wsClient.onStatusChange((status) => {
      setWsConnected(status === 'connected');
    });

    const unsubEvents = wsClient.onEvent((envelope: ServerEnvelope) => {
      const { event_type, payload } = envelope;

      // Handle match start / phase change immediately
      if (event_type === 'MATCH_STARTED' || event_type === 'MATCH_PHASE_CHANGED') {
        const nextPhase = payload?.new_phase || payload?.phase;
        if (nextPhase && nextPhase !== 'LOBBY') {
          isPollingRef.current = false;
          navigate(`/battle/${match.id}${isHostMode() ? '?host=1' : ''}`);
          return;
        }
      }

      // If any lobby event happens, refetch match state immediately
      const lobbyEvents = [
        'MEMBER_JOINED',
        'MEMBER_ASSIGNED',
        'MEMBER_REMOVED',
        'MEMBER_READY_CHANGED',
        'READY_CHANGED',
        'CONFIG_UPDATED',
        'MATCH_LOCKED',
        'TEAM_CREATED',
        'TEAM_DELETED',
      ];
      if (lobbyEvents.includes(event_type)) {
        fetchMatch(false);
      }
    });

    return () => {
      unsubStatus();
      unsubEvents();
    };
  }, [match?.id, fetchMatch, navigate]);

  const copyCode = () => {
    if (match?.room_code) {
      navigator.clipboard.writeText(match.room_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Only the host can create teams after entering the lobby.
  const handleCreateTeam = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!match || !isHost || match.status !== 'LOBBY' || !newTeamName.trim()) return;
    setActionLoading(true);
    try {
      await api.createTeam(match.id, newTeamName.trim());
      setNewTeamName('');
      setShowAddTeamModal(false);
      await fetchMatch();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Tạo đội thất bại');
    } finally {
      setActionLoading(false);
    }
  };

  // Host Action: Delete Team
  const handleDeleteTeam = async (teamId: string) => {
    if (!match || !confirm('Bạn có chắc chắn muốn xóa đội này không?')) return;
    try {
      await api.deleteTeam(match.id, teamId);
      fetchMatch();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Xóa đội thất bại');
    }
  };

  // Team Ready Toggle (Host or Member)
  const handleToggleReady = async (team: Team) => {
    if (!match) return;
    try {
      await api.setTeamReady(match.id, team.id, !team.is_ready);
      fetchMatch();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Cập nhật trạng thái sẵn sàng thất bại');
    }
  };

  // Host Action: Kick Member
  const handleRemoveMember = async (memberId: string) => {
    if (!match || !confirm('Xác nhận mời thành viên này rời khỏi phòng?')) return;
    try {
      await api.removeMember(match.id, memberId);
      fetchMatch();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Xóa thành viên thất bại');
    }
  };

  // Host Action: Assign Member to Team
  const handleAssignMember = async (memberId: string, teamId: string | null, role?: ParticipantRole) => {
    if (!match) return;
    try {
      const member = await api.assignMember(match.id, memberId, { team_id: teamId, role });
      if (activeMember?.id === member.id) {
        setActiveMember(member);
        setActiveMemberState(member);
      }
      await fetchMatch();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Gán thành viên thất bại');
    }
  };

  // Host Action: Toggle Match Lock
  const handleToggleLock = async () => {
    if (!match) return;
    try {
      await api.toggleMatchLock(match.id, !match.is_locked);
      fetchMatch();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Thay đổi trạng thái khóa phòng thất bại');
    }
  };

  // Host Action: Save Config
  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!match || !constraints || editMaxTeams === undefined) return;
    setActionLoading(true);
    try {
      await api.updateMatchConfig(match.id, {
        initial_base_hp: editHp,
        initial_coins: editCoins,
        max_teams: editMaxTeams,
      });
      setShowConfigModal(false);
      fetchMatch();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Cập nhật cấu hình thất bại');
    } finally {
      setActionLoading(false);
    }
  };

  // Host Action: Start Match
  const handleStartMatch = async () => {
    if (!match) return;
    setActionLoading(true);
    try {
      const updated = await api.startMatch(match.id);
      navigate(`/battle/${updated.id}${isHostMode() ? '?host=1' : ''}`);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Không thể bắt đầu trận đấu');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="lobby-page-state" style={{ maxWidth: '600px', margin: '100px auto', textAlign: 'center' }}>
        <RefreshCw size={36} className="animate-spin text-cyan-400" style={{ margin: '0 auto 16px' }} />
        <h2>Đang đồng bộ phòng chờ chiến thuật...</h2>
      </div>
    );
  }

  if (error || !match) {
    return (
      <div className="lobby-page-state lobby-error-state" style={{ maxWidth: '520px', margin: '100px auto', padding: '0 20px' }}>
        <div className="glass-panel" style={{ padding: '36px', textAlign: 'center' }}>
          <AlertCircle size={48} style={{ color: 'var(--accent-rose)', margin: '0 auto 16px' }} />
          <h2 style={{ marginBottom: '10px' }}>Không tìm thấy phòng đấu</h2>
          <p style={{ color: 'var(--text-muted)', marginBottom: '24px' }}>{error || 'Không thể tải dữ liệu phòng đấu.'}</p>
          <button onClick={() => navigate('/join')} className="btn-primary" style={{ padding: '12px 24px' }}>
            Thử mã phòng khác
          </button>
        </div>
      </div>
    );
  }

  // Pre-conditions for Start button
  const minTeamsRequired = match.configuration.min_teams || constraints?.min_teams_to_start || 2;
  const currentTeams = match.teams || [];
  const isPlayer = !!activeMember && match.all_members?.some(member => member.id === activeMember.id) &&
    (activeMember.role === 'MENTOR' || activeMember.role === 'MENTEE');
  const canCreateTeam = isHost && match.status === 'LOBBY';
  const invitationUrl = inviteTeam ? teamInvitationUrl(window.location.origin, match.room_code, inviteTeam.id) : '';
  const hasEnoughTeams = currentTeams.length >= minTeamsRequired;
  const allTeamsReady = currentTeams.length > 0 && currentTeams.every((t) => t.is_ready);
  const minPlayersPerTeam = 1;
  const allTeamsStaffed = currentTeams.every(teamHasPlayers);
  const hasCapacity = currentTeams.length <= match.configuration.max_teams;

  const canStart = match.status === 'LOBBY' && hasEnoughTeams && hasCapacity && allTeamsReady && allTeamsStaffed;

  let startRequirementMessage = '';
  if (!hasCapacity) {
    startRequirementMessage = 'Số đội vượt quá sức chứa của phòng';
  } else if (!hasEnoughTeams) {
    startRequirementMessage = `Cần thêm ${minTeamsRequired - currentTeams.length} đội để đạt tối thiểu ${minTeamsRequired} đội`;
  } else if (!allTeamsStaffed) {
    startRequirementMessage = `Mỗi đội phải có ít nhất ${minPlayersPerTeam} thành viên`;
  } else if (!allTeamsReady) {
    startRequirementMessage = 'Tất cả các đội cần bấm SẴN SÀNG trước khi khởi tranh trận đấu';
  }

  const phaseDisplayNames: Record<string, string> = {
    LOBBY: 'Sảnh chờ (Lobby)',
    PREPARATION: 'Chuẩn bị (Preparation)',
    BUILD_AND_SCOUT: 'Xây dựng & Do thám',
    WAR: 'Chiến tranh (War)',
    FINAL_ASSAULT: 'Tổng công kích',
    RESULTS: 'Kết quả (Results)',
  };

  return (
    <div className="lobby-page" style={{ maxWidth: '1240px', margin: '0 auto', padding: '32px 20px' }}>
      {/* Host / Participant Role Notice */}
      <div className="lobby-status-bar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {isHost ? (
            <span className="badge badge-amber" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Shield size={14} /> Quyền Quản Trị Trận Đấu (Host)
            </span>
          ) : (
            <span className="badge badge-cyan" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Users size={14} /> Chiến binh tham gia: {activeMember ? activeMember.display_name : 'Khách vãng lai'}
            </span>
          )}
          {match.is_locked && (
            <span className="badge badge-rose" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Lock size={12} /> Phòng Đang Khóa
            </span>
          )}
        </div>

        <div className="lobby-sync-status" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem' }}>
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: wsConnected ? 'var(--accent-emerald, #10b981)' : 'var(--accent-amber, #f59e0b)',
              display: 'inline-block',
              boxShadow: wsConnected ? '0 0 8px #10b981' : 'none',
            }}
          />
          <span style={{ color: wsConnected ? 'var(--accent-emerald, #10b981)' : 'var(--text-dim)' }}>
            {wsConnected ? 'Realtime WebSocket' : 'Đang kết nối... (Đồng bộ 2s)'}
          </span>
        </div>
      </div>

      {/* Lobby Header */}
      <div
        className="glass-panel"
        data-lobby-panel="hero"
        style={{
          padding: '24px 32px',
          marginBottom: '28px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '20px',
        }}
      >
        <div className="lobby-title-group">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
            <span className="badge badge-cyan">{phaseDisplayNames[match.phase] || match.phase}</span>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Teams: {currentTeams.length} / {match.configuration.max_teams}
            </span>
          </div>
          <h1 style={{ fontSize: '2.2rem', fontWeight: 800 }}>{match.name}</h1>
        </div>

        {/* Room Code Card */}
        <div
          className="lobby-room-code"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            background: 'rgba(0, 0, 0, 0.45)',
            padding: '12px 20px',
            borderRadius: '12px',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontWeight: 600 }}>MÃ PHÒNG ĐẤU</div>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '1.6rem',
                fontWeight: 800,
                color: 'var(--accent-cyan)',
                letterSpacing: '0.08em',
              }}
            >
              {match.room_code}
            </div>
          </div>
          <button onClick={copyCode} className="btn-secondary" style={{ padding: '8px 14px' }} title="Sao chép mã phòng">
            <Copy size={16} /> {copied ? 'Đã chép!' : 'Sao chép'}
          </button>
        </div>
      </div>

      {/* Host Controls Strip (if Host) */}
      {isHost && (
        <div
          className="glass-panel"
          data-lobby-panel="host"
          style={{
            padding: '16px 24px',
            marginBottom: '28px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px',
            background: 'rgba(245, 158, 11, 0.05)',
            borderColor: 'rgba(245, 158, 11, 0.2)',
          }}
        >
          <div className="lobby-host-buttons" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span className="lobby-host-title" style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--accent-amber)' }}>Thao tác Host:</span>
            <button
              onClick={() => setShowAddTeamModal(true)}
              disabled={!canCreateTeam || currentTeams.length >= match.configuration.max_teams}
              className="btn-primary"
              style={{ padding: '8px 16px', fontSize: '0.85rem' }}
            >
              <Plus size={15} /> Thêm đội
            </button>
            <button
              onClick={() => {
                setEditHp(match.configuration.initial_base_hp);
                setEditCoins(match.configuration.initial_coins);
                setEditMaxTeams(match.configuration.max_teams);
                setShowConfigModal(true);
              }}
              className="btn-secondary"
              style={{ padding: '8px 16px', fontSize: '0.85rem' }}
            >
              <Settings size={15} /> Cấu hình trận
            </button>
            <button
              onClick={handleToggleLock}
              className="btn-secondary"
              style={{ padding: '8px 16px', fontSize: '0.85rem' }}
            >
              {match.is_locked ? <Unlock size={15} /> : <Lock size={15} />}
              {match.is_locked ? 'Mở khóa phòng' : 'Khóa nhận người'}
            </button>
          </div>

          <div className="lobby-host-stats">
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Máu khởi điểm: <strong>{match.configuration.initial_base_hp}</strong> | Coin khởi điểm: <strong>{match.configuration.initial_coins}</strong>
            </span>
          </div>
        </div>
      )}

      {/* Squad Cards Grid */}
      <div className="lobby-roster" style={{ marginBottom: '32px' }}>
        <div className="lobby-roster-heading" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h2 style={{ fontSize: '1.3rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Users size={20} style={{ color: 'var(--accent-cyan)' }} /> Danh sách Đội hình ({currentTeams.length})
          </h2>
          {canCreateTeam && (
            <button
              onClick={() => setShowAddTeamModal(true)}
              disabled={currentTeams.length >= match.configuration.max_teams}
              className="btn-secondary"
              style={{ padding: '6px 14px', fontSize: '0.8rem' }}
            >
              <Plus size={14} /> Thêm nhanh đội
            </button>
          )}
        </div>

        {currentTeams.length >= match.configuration.max_teams && (
          <p className="lobby-capacity-note" role="status">Phòng đã đủ đội. Bạn vẫn có thể tham gia đội còn chỗ.</p>
        )}
        {currentTeams.length === 0 ? (
          <div className="glass-panel lobby-empty-state" style={{ padding: '48px', textAlign: 'center' }}>
            <Users size={40} style={{ color: 'var(--text-dim)', margin: '0 auto 12px' }} />
            <h3 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>Chưa có đội hình nào</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '20px' }}>
              {isHost
                ? `Hãy tạo ít nhất ${minTeamsRequired} đội cho giải đấu bằng nút bên dưới.`
                : 'Đang chờ Host khởi tạo danh sách đội. Người chơi chỉ được tạo đội ở bước tham gia ban đầu.'}
            </p>
            {canCreateTeam && (
              <button onClick={() => setShowAddTeamModal(true)} className="btn-primary" style={{ padding: '10px 22px' }}>
                <Plus size={16} /> Tạo đội đầu tiên
              </button>
            )}
          </div>
        ) : (
          <div className="lobby-team-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
            {currentTeams.map((team, teamIndex) => {
              const mentor = team.members?.find((m) => m.role === 'MENTOR');
              const mentees = team.members?.filter((m) => m.role === 'MENTEE') || [];

              const isMyTeam = activeMember && activeMember.team_id === team.id;

              return (
                <div
                  key={team.id}
                  className={`glass-panel lobby-team-card${isMyTeam ? ' is-my-team' : ''}`}
                  style={{
                    padding: '24px',
                    border: isMyTeam ? '1px solid var(--accent-cyan)' : '1px solid var(--border-subtle)',
                    background: isMyTeam ? 'rgba(56, 189, 248, 0.04)' : undefined,
                    position: 'relative',
                  }}
                >
                  {/* Squad Header */}
                  <div className="lobby-team-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <div className="lobby-team-title-wrap">
                      <h3 className="lobby-team-name" style={{ fontSize: '1.2rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{color:PALETTE[teamIndex]}}>{teamLabel(teamIndex)}</span> {team.name}
                        {isMyTeam && <span className="badge badge-cyan" style={{ fontSize: '0.7rem' }}>ĐỘI CỦA TÔI</span>}
                      </h3>
                      <div className="lobby-team-meta" style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                        Thành viên: {activeMemberCount(team)} / {match.configuration.max_players_per_team} · Máu: {team.base_hp} HP {team.coins !== undefined && `| Coin: ${team.coins}`}
                      </div>
                    </div>

                    <div className="lobby-team-state-tools" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {team.is_ready && teamHasPlayers(team) ? (
                        <span className="badge badge-emerald" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <CheckCircle2 size={12} /> Sẵn sàng
                        </span>
                      ) : (
                        <span className="badge badge-amber" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <AlertCircle size={12} /> Đang chờ
                        </span>
                      )}

                      {isHost && (
                        <button
                          onClick={() => handleDeleteTeam(team.id)}
                          style={{
                            background: 'transparent',
                            border: 'none',
                            color: 'var(--text-dim)',
                            cursor: 'pointer',
                            padding: '4px',
                          }}
                          title="Xóa đội này"
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  </div>

                  {match.status === 'LOBBY' && isPlayer && activeMember && !isMyTeam && (
                    <button className="btn-secondary" style={{ width: '100%', marginBottom: '14px' }}
                      disabled={actionLoading || !!teamJoinIssue(team, activeMember.role, match.configuration.max_players_per_team)}
                      onClick={() => handleAssignMember(activeMember.id, team.id, activeMember.role)}>
                      {teamJoinIssue(team, activeMember.role, match.configuration.max_players_per_team) || 'Tham gia đội này'}
                    </button>
                  )}
                  {match.status === 'LOBBY' && (isHost || (isMyTeam && isPlayer)) && (
                    <button className="btn-secondary" style={{ width: '100%', marginBottom: '14px' }}
                      disabled={match.is_locked || (team.members?.length || 0) >= match.configuration.max_players_per_team}
                      onClick={() => { setInviteTeam(team); setInviteCopied(false); setInviteError(''); }}>
                      <Users size={15} /> {match.is_locked ? 'Phòng đã khóa nhận người' : (team.members?.length || 0) >= match.configuration.max_players_per_team ? 'Đội đã đầy' : 'Mời vào đội'}
                    </button>
                  )}

                  {/* Mentor Block (§2.1: max 1 mentor) */}
                  <div className="lobby-member-group lobby-mentor-group" style={{ marginBottom: '14px' }}>
                    <div className="lobby-role-label lobby-mentor-label" style={{ fontSize: '0.75rem', color: 'var(--accent-amber)', fontWeight: 700, marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Crown size={12} /> MENTOR CỐ VẤN
                    </div>
                    {mentor ? (
                      <div
                        className="lobby-member-row lobby-mentor-row"
                        style={{
                          fontSize: '0.9rem',
                          color: '#fff',
                          background: 'rgba(245, 158, 11, 0.12)',
                          border: '1px solid rgba(245, 158, 11, 0.25)',
                          padding: '8px 12px',
                          borderRadius: '8px',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                        }}
                      >
                        <span style={{ fontWeight: 600 }}>{mentor.display_name}</span>
                        {isHost && (
                          <button
                            onClick={() => handleRemoveMember(mentor.id)}
                            style={{ background: 'transparent', border: 'none', color: 'var(--accent-rose)', cursor: 'pointer' }}
                            title="Mời mentor rời đội"
                          >
                            <UserMinus size={14} />
                          </button>
                        )}
                      </div>
                    ) : (
                      <div
                        className="lobby-member-row lobby-empty-member"
                        style={{
                          fontSize: '0.85rem',
                          color: 'var(--text-dim)',
                          background: 'rgba(0, 0, 0, 0.2)',
                          padding: '8px 12px',
                          borderRadius: '8px',
                          fontStyle: 'italic',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                        }}
                      >
                        <span>Chưa có Mentor</span>
                        {isPlayer && activeMember && !activeMember.team_id && match.status === 'LOBBY' && (
                          <button
                            onClick={() => handleAssignMember(activeMember.id, team.id, 'MENTOR')}
                            className="btn-secondary"
                            style={{ padding: '4px 10px', fontSize: '0.75rem', color: 'var(--accent-amber)' }}
                          >
                            Nhận vai Mentor
                          </button>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Mentees Block */}
                  <div className="lobby-member-group lobby-mentee-group" style={{ marginBottom: '16px' }}>
                    <div className="lobby-role-label lobby-mentee-label" style={{ fontSize: '0.75rem', color: 'var(--accent-cyan)', fontWeight: 700, marginBottom: '6px' }}>
                      CHIẾN BINH MENTEE ({mentees.length})
                    </div>
                    {mentees.length === 0 ? (
                      <div className="lobby-empty-member" style={{ fontSize: '0.85rem', color: 'var(--text-dim)', fontStyle: 'italic', padding: '6px 0' }}>
                        Chưa có mentee nào
                      </div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        {mentees.map((m) => (
                          <div
                            className="lobby-member-row"
                            key={m.id}
                            style={{
                              fontSize: '0.85rem',
                              color: 'var(--text-main)',
                              background: 'rgba(0, 0, 0, 0.25)',
                              padding: '6px 12px',
                              borderRadius: '6px',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                            }}
                          >
                            <span>{m.display_name}</span>
                            {isHost && (
                              <button
                                onClick={() => handleRemoveMember(m.id)}
                                style={{ background: 'transparent', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}
                                title="Mời thành viên rời đội"
                              >
                                <UserMinus size={14} />
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Ready Toggle Button */}
                  <div className="lobby-ready-row" style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '14px', textAlign: 'right' }}>
                    {(isHost || isMyTeam) && (
                      <button
                        onClick={() => handleToggleReady(team)}
                        disabled={!team.is_ready && !teamHasPlayers(team)}
                        className={team.is_ready ? 'btn-secondary' : 'btn-primary'}
                        data-ready={team.is_ready ? 'true' : 'false'}
                        style={{ padding: '8px 16px', fontSize: '0.85rem', width: '100%' }}
                      >
                        <CheckCircle2 size={14} /> {team.is_ready ? 'Hủy sẵn sàng' : 'Xác nhận Đội đã Sẵn sàng'}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Unassigned Members Strip (if any) */}
      {match.unassigned_members && match.unassigned_members.length > 0 && (
        <div className="glass-panel lobby-unassigned" style={{ padding: '24px', marginBottom: '32px' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '14px', color: 'var(--accent-purple)' }}>
            Thành viên chưa gán đội ({match.unassigned_members.length})
          </h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
            {match.unassigned_members.map((m) => (
              <div
                className="lobby-unassigned-member"
                key={m.id}
                style={{
                  background: 'rgba(0, 0, 0, 0.35)',
                  padding: '8px 14px',
                  borderRadius: '8px',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  fontSize: '0.85rem',
                }}
              >
                <span><strong>{m.display_name}</strong> ({m.role})</span>
                {isHost && (
                  <select
                    onChange={(e) => {
                      if (e.target.value) {
                        handleAssignMember(m.id, e.target.value, m.role);
                      }
                    }}
                    defaultValue=""
                    style={{
                      background: '#0d1527',
                      color: '#fff',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '6px',
                      padding: '4px 8px',
                      fontSize: '0.8rem',
                    }}
                  >
                    <option value="" disabled>Gán vào đội...</option>
                    {match.teams.map((t) => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                )}
                {isHost && (
                  <button
                    onClick={() => handleRemoveMember(m.id)}
                    style={{ background: 'transparent', border: 'none', color: 'var(--accent-rose)', cursor: 'pointer' }}
                    title="Mời rời phòng"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action Footer (Host Mission Launch) */}
      <div
        className="glass-panel"
        data-lobby-panel="launch"
        style={{
          padding: '24px 32px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '20px',
        }}
      >
        <div>
          <div style={{ fontWeight: 700, fontSize: '1.05rem', marginBottom: '4px' }}>
            {match.status === 'LOBBY' ? 'Trạng thái sẵn sàng khởi tranh' : `Trạng thái: ${match.status}`}
          </div>
          <div className={canStart ? 'lobby-launch-status is-ready' : 'lobby-launch-status'} style={{ fontSize: '0.9rem', color: canStart ? 'var(--accent-emerald)' : 'var(--text-muted)' }}>
            {canStart ? 'Tất cả các đội đã sẵn sàng! Đã đủ điều kiện bắt đầu trận đấu.' : startRequirementMessage}
          </div>
        </div>

        <div className="lobby-launch-action" style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
          {isHost ? (
            <button
              onClick={handleStartMatch}
              disabled={!canStart || actionLoading}
              className="btn-primary"
              style={{
                padding: '14px 28px',
                fontSize: '1.05rem',
                background: canStart ? undefined : 'rgba(255, 255, 255, 0.1)',
                cursor: canStart ? 'pointer' : 'not-allowed',
              }}
            >
              <Play size={18} /> {actionLoading ? 'Đang khởi tạo trận đấu...' : 'BẮT ĐẦU TRẬN ĐẤU (CHUẨN BỊ)'}
            </button>
          ) : (
            <div style={{ color: 'var(--text-dim)', fontSize: '0.9rem' }}>
              Đang đợi Quản trị viên (Host) phát lệnh khởi tranh...
            </div>
          )}
        </div>
      </div>

      {/* ADD SQUAD MODAL */}
      {inviteTeam && (
        <div className="lobby-modal-backdrop" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '20px' }}>
          <div ref={inviteDialogRef} className="glass-panel lobby-modal-card" role="dialog" aria-modal="true" aria-labelledby="invite-title" style={{ width: '100%', maxWidth: '480px', padding: '28px' }}>
            <h3 id="invite-title">Mời vào đội {inviteTeam.name}</h3>
            <p style={{ margin: '12px 0', color: 'var(--text-muted)' }}>Gửi liên kết này cho đồng đội. Khi mở, mã phòng và đội của bạn sẽ được chọn sẵn; người nhận tự nhập tên và chọn vai trò.</p>
            <label htmlFor="team-invitation">Liên kết mời vào đội</label>
            <input id="team-invitation" readOnly value={invitationUrl} onFocus={e => e.target.select()} style={{ width: '100%', margin: '10px 0', padding: '10px' }} />
            {inviteError && <p role="status">{inviteError}</p>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '12px' }}>
              <button className="btn-secondary" onClick={() => setInviteTeam(null)}>Đóng</button>
              <button className="btn-primary" onClick={async () => {
                try { await navigator.clipboard.writeText(invitationUrl); setInviteCopied(true); setInviteError(''); }
                catch { setInviteError('Không thể tự sao chép. Hãy chọn và sao chép liên kết ở trên.'); }
              }}><Copy size={15} /> {inviteCopied ? 'Đã sao chép!' : 'Sao chép lời mời'}</button>
            </div>
          </div>
        </div>
      )}
      {showAddTeamModal && canCreateTeam && (
        <div
          className="lobby-modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
        >
          <div className="glass-panel lobby-modal-card" style={{ width: '100%', maxWidth: '440px', padding: '32px', position: 'relative' }}>
            <button
              onClick={() => setShowAddTeamModal(false)}
              style={{
                position: 'absolute',
                right: '18px',
                top: '18px',
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                cursor: 'pointer',
              }}
            >
              <X size={20} />
            </button>

            <h3 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: '6px' }}>Thêm Đội Hình Mới</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '20px' }}>
              Khởi tạo thêm một đội cho trận đấu (tối đa {match.configuration.max_teams} đội).
            </p>

            <form onSubmit={handleCreateTeam}>
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                  TÊN ĐỘI
                </label>
                <input
                  type="text"
                  required
                  maxLength={50}
                  placeholder="Ví dụ: Đội Rồng Lửa"
                  value={newTeamName}
                  onChange={(e) => setNewTeamName(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    background: 'rgba(0, 0, 0, 0.3)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '8px',
                    color: '#fff',
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={() => setShowAddTeamModal(false)}
                  className="btn-secondary"
                  style={{ padding: '8px 18px' }}
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="btn-primary"
                  style={{ padding: '8px 20px' }}
                >
                  {actionLoading ? 'Đang tạo...' : 'Tạo Đội'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT CONFIG MODAL */}
      {showConfigModal && (
        <div
          className="lobby-modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
        >
          <div className="glass-panel lobby-modal-card" style={{ width: '100%', maxWidth: '480px', padding: '32px', position: 'relative' }}>
            <button
              onClick={() => setShowConfigModal(false)}
              style={{
                position: 'absolute',
                right: '18px',
                top: '18px',
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                cursor: 'pointer',
              }}
            >
              <X size={20} />
            </button>

            <h3 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: '6px' }}>Chỉnh Sửa Cấu Hình Trận Đấu</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '20px' }}>
              Điều chỉnh các thông số cân bằng trước khi trận bắt đầu (§7.4).
            </p>

            <form onSubmit={handleSaveConfig}>
              <MaximumTeamsSelect value={editMaxTeams} onChange={setEditMaxTeams}
                constraints={constraints} minimum={Math.max(minTeamsRequired, currentTeams.length)} error={constraintsError} />

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '24px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                    MÁU CĂN CỨ KHỞI ĐIỂM
                  </label>
                  <input
                    type="number"
                    min={100}
                    max={2000}
                    step={50}
                    value={editHp}
                    onChange={(e) => setEditHp(Number(e.target.value))}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      background: 'rgba(0, 0, 0, 0.3)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '8px',
                      color: '#fff',
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                    SỐ COIN KHỞI ĐIỂM
                  </label>
                  <input
                    type="number"
                    min={50}
                    max={1000}
                    step={25}
                    value={editCoins}
                    onChange={(e) => setEditCoins(Number(e.target.value))}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      background: 'rgba(0, 0, 0, 0.3)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '8px',
                      color: '#fff',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={() => setShowConfigModal(false)}
                  className="btn-secondary"
                  style={{ padding: '8px 18px' }}
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || !constraints}
                  className="btn-primary"
                  style={{ padding: '8px 20px' }}
                >
                  {actionLoading ? 'Đang lưu...' : 'Lưu cấu hình'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
