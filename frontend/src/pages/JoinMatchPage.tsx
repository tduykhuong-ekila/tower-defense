import React, { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  CheckCircle2,
  Crown,
  Eye,
  Key,
  LogIn,
  ShieldAlert,
  ShieldCheck,
  Swords,
  User,
  Users,
} from 'lucide-react';
import { api, clearHostToken, setActiveMember, setParticipantToken } from '../services/api';
import { Match, ParticipantRole, Team } from '../types/match';
import { entityArtwork } from '../game/entityArtwork';
import { teamJoinIssue } from '../game/teamJoining';
import './JoinMatchPage.css';

export const JoinMatchPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const [roomCode, setRoomCode] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState<ParticipantRole>('MENTEE');
  const [selectedTeamId, setSelectedTeamId] = useState<string>('');
  const [newTeamName, setNewTeamName] = useState('');
  const verificationId = useRef(0);

  const [verifiedMatch, setVerifiedMatch] = useState<Match | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Check URL query parameters for ?code=XXXXXX
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const codeParam = params.get('code');
    if (codeParam) {
      const code = codeParam.toUpperCase().trim();
      setRoomCode(code);
      verifyCode(code, params.get('team'));
    }
  }, [location.search]);

  // When roomCode reaches 6 chars, auto-verify match
  const verifyCode = async (code: string, invitedTeamId: string | null = null) => {
    const requestId = ++verificationId.current;
    setVerifiedMatch(null);
    setSelectedTeamId('');
    if (code.length !== 6) {
      setIsVerifying(false);
      return;
    }
    setIsVerifying(true);
    setError(null);
    try {
      const match = await api.getMatchByCode(code);
      if (requestId !== verificationId.current) return;
      setVerifiedMatch(match);
      if (invitedTeamId) {
        if (match.teams.some(team => team.id === invitedTeamId)) {
          setSelectedTeamId(invitedTeamId);
        } else {
          setError('Đội trong lời mời không còn tồn tại. Bạn có thể chọn đội khác hoặc tạo đội mới.');
        }
      }
    } catch {
      if (requestId !== verificationId.current) return;
      setVerifiedMatch(null);
      setError(`Không tìm thấy phòng đấu với mã "${code}" hoặc phòng đã đóng.`);
    } finally {
      if (requestId === verificationId.current) setIsVerifying(false);
    }
  };

  const handleRoomCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value.toUpperCase().trim().slice(0, 6);
    setRoomCode(val);
    verifyCode(val);
  };

  const returningMember = verifiedMatch?.all_members?.find(member =>
    member.role !== 'HOST' && member.display_name === displayName.trim());

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!roomCode.trim() || !displayName.trim()) {
      setError('Vui lòng cung cấp cả Mã phòng và Tên hiển thị của bạn.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // 1. Ensure we have the target match
      let match = verifiedMatch;
      if (!match) {
        match = await api.getMatchByCode(roomCode);
      }
      const resuming = match.all_members?.some(member =>
        member.role !== 'HOST' && member.display_name === displayName.trim());
      const creatingTeam = !resuming && role !== 'SPECTATOR' && selectedTeamId === 'new';
      if (creatingTeam && !newTeamName.trim()) throw new Error('Vui lòng nhập tên đội mới.');
      const team = match.teams.find(team => team.id === selectedTeamId);
      if (!resuming && role !== 'SPECTATOR' && team) {
        const issue = teamJoinIssue(team, role, match.configuration.max_players_per_team);
        if (issue) throw new Error(issue);
      }

      // 2. Call join endpoint
      const joinRes = await api.joinMatch(match.id, {
        room_code: roomCode,
        display_name: displayName,
        team_id: resuming || role === 'SPECTATOR' || creatingTeam ? null : selectedTeamId || null,
        ...(creatingTeam ? { new_team_name: newTeamName.trim() } : {}),
        role: role,
      });

      // 3. Save participant token & member profile
      // A previous Host session in this browser tab must not leak into player play.
      clearHostToken();
      setParticipantToken(joinRes.participant_token);
      setActiveMember(joinRes.member);

      // 4. Navigate to squad lobby
      const destination = joinRes.match.status === 'FINISHED' ? 'results'
        : ['ACTIVE', 'PAUSED'].includes(joinRes.match.status) ? 'battle' : 'lobby';
      navigate(`/${destination}/${match.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Tham gia phòng thất bại');
    } finally {
      setLoading(false);
    }
  };

  const selectedTeam = verifiedMatch?.teams.find(team => team.id === selectedTeamId);
  const selectedTeamIssue = !returningMember && selectedTeam && role !== 'SPECTATOR'
    ? teamJoinIssue(selectedTeam, role, verifiedMatch!.configuration.max_players_per_team) : null;

  return (
    <main className="join-page">
      <div className="join-layout">
        <aside className="join-intro">
          <div className="join-eyebrow"><ShieldCheck size={15} /> THƯ MỜI TỪ CHIẾN TRƯỜNG</div>
          <h1>TẬP HỢP<br /><span>ĐỘI NGŨ</span></h1>
          <p className="join-intro-copy">Báo danh, chọn vai trò và sát cánh cùng đồng đội để giữ vững căn cứ.</p>

          <div className="join-artboard" aria-hidden="true">
            <div className="join-art-glow" />
            <svg className="join-art-road" viewBox="0 0 500 300" preserveAspectRatio="none">
              <path className="join-art-road-shadow" d="M-15 263 C120 237 118 161 224 167 S378 188 515 38" />
              <path className="join-art-road-fill" d="M-15 263 C120 237 118 161 224 167 S378 188 515 38" />
              <path className="join-art-road-center" d="M-15 263 C120 237 118 161 224 167 S378 188 515 38" />
            </svg>
            <img className="join-art-tree join-art-tree-left" src="/assets/woodland/tree-1.svg" alt="" />
            <img className="join-art-tree join-art-tree-right" src="/assets/woodland/tree-0.svg" alt="" />
            <img className="join-art-base" src="/assets/woodland/base-2.svg" alt="" />
            <img className="join-art-tower" src={entityArtwork('mg_tower')} alt="" />
            <img className="join-art-tank" src={entityArtwork('tank')} alt="" />
            <span className="join-art-location"><i /> CĂN CỨ ĐỒNG MINH</span>
            <div className="join-art-caption"><span className="join-art-caption-mark"><Swords size={16} /></span><span><b>SẴN SÀNG XUẤT KÍCH</b><small>CHIẾN THUẬT BẮT ĐẦU TỪ ĐÂY</small></span></div>
          </div>

          <div className="join-field-notes">
            <div><span>01</span><p><b>Báo danh</b><small>Nhập mã phòng và tên hiển thị</small></p></div>
            <div><span>02</span><p><b>Chọn vị trí</b><small>Gia nhập đội và chọn vai trò</small></p></div>
            <div><span>03</span><p><b>Ra chiến trường</b><small>Hội quân tại sảnh chờ</small></p></div>
          </div>
        </aside>

        <section className="join-form-panel">
          <header className="join-form-heading">
            <div className="join-form-crest"><Users size={22} /></div>
            <div><span>PHIẾU ĐĂNG KÝ</span><h2>Vào Phòng Đấu</h2><p>Thiết lập hồ sơ chiến binh của bạn</p></div>
          </header>

          {error && <div className="join-error"><ShieldAlert size={18} /> <span>{error}</span></div>}

          <form onSubmit={handleJoin} className="join-form">
            <div className="join-field">
              <div className="join-label-row">
                <label htmlFor="join-room-code">MÃ PHÒNG <small>6 KÝ TỰ</small></label>
                {isVerifying && <span className="join-verifying">Đang kiểm tra...</span>}
                {verifiedMatch && <span className="join-verified"><CheckCircle2 size={13} /> {verifiedMatch.name}</span>}
              </div>
              <div className={`join-input-wrap join-code-wrap${verifiedMatch ? ' is-verified' : ''}`}>
                <Key size={18} />
                <input id="join-room-code" type="text" required maxLength={6} value={roomCode} onChange={handleRoomCodeChange} placeholder="Ví dụ: 7X8K2M" autoComplete="off" />
              </div>
            </div>

            <div className="join-field">
              <label htmlFor="join-display-name">TÊN HIỂN THỊ</label>
              <div className="join-input-wrap">
                <User size={18} />
                <input id="join-display-name" type="text" required value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Ví dụ: Hoàng Long" autoComplete="name" />
              </div>
            </div>

            {returningMember && <p className="join-mentor-note" role="status">Đã tìm thấy phiên chơi của bạn. Vào lại để tiếp tục với đội và vai trò cũ.</p>}

            {verifiedMatch && !returningMember && role !== 'SPECTATOR' && (
              <div className="join-field">
                <label htmlFor="join-team">CHỌN ĐỘI GIA NHẬP</label>
                <div className="join-input-wrap join-select-wrap">
                  <Users size={18} />
                  <select id="join-team" value={selectedTeamId} onChange={(e) => setSelectedTeamId(e.target.value)}>
                    {verifiedMatch.teams.map((t: Team) => {
                      const issue = teamJoinIssue(t, role, verifiedMatch.configuration.max_players_per_team);
                      return <option key={t.id} value={t.id} disabled={!!issue}>{t.name} ({t.members?.length || 0}/{verifiedMatch.configuration.max_players_per_team}) {issue ? `— ${issue}` : ''}</option>;
                    })}
                    {verifiedMatch.status === 'LOBBY' && !verifiedMatch.is_locked && verifiedMatch.teams.length < verifiedMatch.configuration.max_teams && (
                      <option value="new">+ Tạo đội mới và tham gia</option>
                    )}
                    <option value="">Gia nhập tự do (Gán đội sau trong phòng chờ)</option>
                  </select>
                </div>
                {selectedTeamId === 'new' && (
                  <div className="join-new-team">
                    <label htmlFor="join-new-team-name">TÊN ĐỘI MỚI</label>
                    <div className="join-input-wrap">
                      <Users size={18} />
                      <input id="join-new-team-name" required maxLength={50} value={newTeamName} onChange={e => setNewTeamName(e.target.value)} placeholder="Ví dụ: Đội Rồng Lửa" />
                    </div>
                    <p>Bạn sẽ tự động tham gia đội vừa tạo với vai trò đã chọn.</p>
                  </div>
                )}
                {verifiedMatch.teams.length >= verifiedMatch.configuration.max_teams && <p className="join-mentor-note">Phòng đã đủ đội. Hãy chọn đội còn chỗ.</p>}
                {selectedTeamIssue && <p className="join-mentor-note" role="status">{selectedTeamIssue}. Hãy chọn đội khác hoặc đổi vai trò.</p>}
              </div>
            )}

            <fieldset className="join-role-fieldset" hidden={!!returningMember}>
              <legend>VAI TRÒ CHIẾN ĐẤU</legend>
              <div className="join-role-grid">
                <button type="button" aria-pressed={role === 'MENTEE'} onClick={() => setRole('MENTEE')} className={`join-role-card${role === 'MENTEE' ? ' is-selected mentee' : ''}`}>
                  <Swords size={19} /><b>Mentee</b><small>Chiến binh</small>
                </button>
                <button type="button" aria-pressed={role === 'MENTOR'} onClick={() => setRole('MENTOR')} className={`join-role-card${role === 'MENTOR' ? ' is-selected mentor' : ''}`}>
                  <Crown size={19} /><b>Mentor</b><small>Cố vấn</small>
                </button>
                <button type="button" aria-pressed={role === 'SPECTATOR'} onClick={() => setRole('SPECTATOR')} className={`join-role-card${role === 'SPECTATOR' ? ' is-selected spectator' : ''}`}>
                  <Eye size={19} /><b>Khán giả</b><small>Theo dõi trận đấu</small>
                </button>
              </div>
              {role === 'MENTOR' && <p className="join-mentor-note">Mỗi đội chỉ có tối đa 1 Mentor cố vấn.</p>}
            </fieldset>

            <button type="submit" disabled={loading || isVerifying || !!selectedTeamIssue || (!!verifiedMatch?.is_locked && !returningMember)} className="btn-primary join-submit">
              <LogIn size={18} /> {loading ? 'Đang kết nối phòng chờ...' : returningMember ? 'Tiếp tục phiên chơi' : 'Vào Phòng Chờ'}
            </button>
            <div className="join-form-footnote"><ShieldCheck size={14} /> Để vào lại phiên chơi, nhập cùng mã phòng và đúng tên hiển thị</div>
          </form>
        </section>
      </div>
    </main>
  );
};
