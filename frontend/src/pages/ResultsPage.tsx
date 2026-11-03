import React, { useEffect, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import {
  Trophy,
  Award,
  RotateCcw,
  Home,
  Loader2,
  Tv,
  Target,
  ShieldCheck,
  Zap,
  BookOpen,
  Users2,
  Clock,
  Sparkles,
  Swords,
  Castle,
} from 'lucide-react';
import { MatchResultsApiResponse, MatchAward, MatchResultRecord } from '../types/combat';
import { api } from '../services/api';
import './ResultsPage.css';

export const ResultsPage: React.FC = () => {
  const { matchId } = useParams<{ matchId?: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState<boolean>(!!matchId);
  const [apiData, setApiData] = useState<MatchResultsApiResponse | null>(null);
  const [loadError, setLoadError] = useState('');
  const [isProjectorMode, setIsProjectorMode] = useState<boolean>(false);
  const [rematchLoading, setRematchLoading] = useState<boolean>(false);

  // Fallback standings if accessed without matchId
  const defaultStandings: MatchResultRecord[] = [
    {
      id: '1',
      match_id: 'm1',
      final_rank: 1,
      team_id: 't1',
      team_name: 'Đội Rồng Lửa',
      final_score: 420,
      bases_destroyed: 2,
      base_damage_dealt: 850,
      remaining_base_hp: 450,
      correct_answers: 8,
      remaining_coins: 75,
      surviving_towers: 3,
      created_at: '2026-10-16T12:00:00Z',
    },
    {
      id: '2',
      match_id: 'm1',
      final_rank: 2,
      team_id: 't2',
      team_name: 'Chiến Binh Tiên Phong',
      final_score: 310,
      bases_destroyed: 1,
      base_damage_dealt: 540,
      remaining_base_hp: 280,
      correct_answers: 6,
      remaining_coins: 40,
      surviving_towers: 2,
      created_at: '2026-10-16T12:00:00Z',
    },
    {
      id: '3',
      match_id: 'm1',
      final_rank: 3,
      team_id: 't3',
      team_name: 'Vệ Binh Sa Mạc',
      final_score: 195,
      bases_destroyed: 0,
      base_damage_dealt: 290,
      remaining_base_hp: 120,
      correct_answers: 5,
      remaining_coins: 25,
      surviving_towers: 1,
      created_at: '2026-10-16T12:00:00Z',
    },
    {
      id: '4',
      match_id: 'm1',
      final_rank: 4,
      team_id: 't4',
      team_name: 'Quân Đoàn Thép',
      final_score: 110,
      bases_destroyed: 0,
      base_damage_dealt: 110,
      remaining_base_hp: 0,
      correct_answers: 4,
      remaining_coins: 10,
      surviving_towers: 0,
      created_at: '2026-10-16T12:00:00Z',
    },
  ];

  const defaultAwards: MatchAward[] = [
    {
      id: 'BEST_STRATEGIST',
      name: 'Chiến Lược Gia Xuất Sắc',
      description: 'Phá nhiều căn cứ đối thủ và gây sát thương cao nhất trận',
      team_id: 't1',
      team_name: 'Đội Rồng Lửa',
      score: 850,
    },
    {
      id: 'BEST_DEFENSE',
      name: 'Bức Tường Kiên Cố',
      description: 'Bảo vệ căn cứ vững chắc và bảo tồn nhiều tháp phòng thủ nhất',
      team_id: 't1',
      team_name: 'Đội Rồng Lửa',
      score: 450,
    },
    {
      id: 'BEST_COMEBACK',
      name: 'Lội Ngược Dòng Ngoạn Mục',
      description: 'Khởi sắc mạnh mẽ và chiến đấu bền bỉ từ tình thế hiểm nghèo',
      team_id: 't2',
      team_name: 'Chiến Binh Tiên Phong',
      score: 310,
    },
    {
      id: 'KNOWLEDGE_CHAMPION',
      name: 'Quán Quân Tri Thức',
      description: 'Trả lời chính xác nhiều câu hỏi nhất giúp đội chiếm ưu thế',
      team_id: 't1',
      team_name: 'Đội Rồng Lửa',
      score: 8,
    },
    {
      id: 'SYNERGY',
      name: 'Gắn Kết Mentor - Mentee',
      description: 'Sự ăn ý hoàn hảo giữa định hướng của Mentor và tốc độ của Mentee',
      team_id: 't2',
      team_name: 'Chiến Binh Tiên Phong',
      score: 95,
    },
  ];

  useEffect(() => {
    if (!matchId) return;

    let isMounted = true;
    const fetchResults = async () => {
      try {
        const data = await api.getResults(matchId);
        if (isMounted) {
          setApiData(data);
        }
      } catch (err) {
        console.error('Failed to load match results:', err);
        if (isMounted) setLoadError(err instanceof Error ? err.message : 'Không tải được kết quả.');
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchResults();
    return () => {
      isMounted = false;
    };
  }, [matchId]);

  const handleRematch = async () => {
    if (!matchId) return;
    setRematchLoading(true);
    try {
      const res = await api.rematch(matchId);
      alert(`Đã khởi tạo trận tái đấu mới thành công! Mã phòng mới: #${res.new_room_code}`);
      navigate(`/lobby/${res.new_match_id}?host=1`);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Tạo trận tái đấu thất bại');
    } finally {
      setRematchLoading(false);
    }
  };

  const resultsList = matchId ? apiData?.results || [] : defaultStandings;
  const awardsList = matchId ? apiData?.awards || [] : defaultAwards;
  const winnerName = apiData?.winner_team_name || (resultsList.length > 0 ? resultsList[0].team_name : 'Đội Rồng Lửa');
  const durationMinutes = apiData?.duration_seconds ? Math.round(apiData.duration_seconds / 60) : 25;

  const getAwardIcon = (id: string) => {
    switch (id) {
      case 'BEST_STRATEGIST':
        return <Target size={22} style={{ color: 'var(--accent-amber)' }} />;
      case 'BEST_DEFENSE':
        return <ShieldCheck size={22} style={{ color: 'var(--accent-cyan)' }} />;
      case 'BEST_COMEBACK':
        return <Zap size={22} style={{ color: 'var(--accent-purple)' }} />;
      case 'KNOWLEDGE_CHAMPION':
        return <BookOpen size={22} style={{ color: 'var(--accent-emerald)' }} />;
      case 'SYNERGY':
      default:
        return <Users2 size={22} style={{ color: '#f43f5e' }} />;
    }
  };

  if (loading) {
    return (
      <div className="results-page-state" style={{ maxWidth: '600px', margin: '100px auto', textAlign: 'center' }}>
        <Loader2 size={40} className="animate-spin" style={{ color: 'var(--accent-cyan)', margin: '0 auto 16px' }} />
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700 }}>Đang tổng hợp kết quả trận đấu...</h2>
        <p style={{ color: 'var(--text-muted)' }}>Hệ thống đang chốt điểm số và tính toán các danh hiệu vinh danh.</p>
      </div>
    );
  }

  if (matchId && (loadError || !resultsList.length)) {
    return <div className="glass-panel results-page-state results-error-state" style={{maxWidth:600, margin:'80px auto', padding:32}}>
      <h2>{loadError ? 'Không tải được kết quả' : 'Trận đấu đang diễn ra'}</h2>
      <p>{loadError || 'Bảng xếp hạng được chốt khi trận đấu kết thúc.'}</p>
      <Link to={`/battle/${matchId}`}>Trở lại chiến trường →</Link>
    </div>;
  }

  return (
    <div
      className={`results-page${isProjectorMode ? ' is-projector' : ''}`}
      style={{
        maxWidth: isProjectorMode ? '100%' : '1160px',
        margin: '0 auto',
        padding: isProjectorMode ? '40px 60px' : '32px 20px 80px',
        transition: 'all 0.3s ease',
      }}
    >
      {/* Presentation Top Utility Bar */}
      <div
        className="results-utility"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '24px',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="badge badge-amber" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Sparkles size={13} /> LỄ VINH DANH & KẾT QUẢ CHUNG CUỘC (FR-10)
          </span>
          {apiData?.room_code && (
            <span className="badge badge-cyan">Mã phòng: #{apiData.room_code}</span>
          )}
          <span className="badge badge-purple" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Clock size={12} /> Thời gian: {durationMinutes} phút
          </span>
        </div>

        <div className="results-utility-actions" style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <button
            id="btn-toggle-projector-mode"
            onClick={() => setIsProjectorMode(!isProjectorMode)}
            className="btn-secondary"
            style={{
              padding: '8px 16px',
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              background: isProjectorMode ? 'var(--accent-amber)' : undefined,
              color: isProjectorMode ? '#0f172a' : undefined,
              fontWeight: isProjectorMode ? 700 : 500,
            }}
          >
            <Tv size={15} /> {isProjectorMode ? 'Chế Độ Chuẩn' : 'Chế Độ Trình Chiếu (Projector)'}
          </button>

          {matchId && (
            <button
              id="btn-results-rematch"
              onClick={handleRematch}
              disabled={rematchLoading}
              className="btn-primary"
              style={{ padding: '8px 18px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <RotateCcw size={15} /> {rematchLoading ? 'Đang tạo...' : 'Tái Đấu (Rematch)'}
            </button>
          )}
        </div>
      </div>

      {/* 1. Champion Hero Banner */}
      <div
        className="glass-panel"
        data-results-panel="champion"
        style={{
          padding: isProjectorMode ? '60px 40px' : '48px 32px',
          textAlign: 'center',
          marginBottom: '36px',
          position: 'relative',
          overflow: 'hidden',
          background: 'linear-gradient(180deg, rgba(245, 158, 11, 0.12) 0%, rgba(15, 23, 42, 0.8) 100%)',
          border: '2px solid rgba(245, 158, 11, 0.35)',
          boxShadow: '0 20px 40px -15px rgba(245, 158, 11, 0.25)',
        }}
      >
        <div
          className="results-trophy-seal"
          style={{
            position: 'absolute',
            top: 0,
            left: '50%',
            transform: 'translateX(-50%)',
            width: '400px',
            height: '4px',
            background: 'linear-gradient(90deg, #f59e0b, #38bdf8, #ec4899)',
          }}
        />

        <div
          style={{
            width: isProjectorMode ? '90px' : '72px',
            height: isProjectorMode ? '90px' : '72px',
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #f59e0b, #d97706)',
            color: '#0f172a',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '18px',
            boxShadow: '0 0 30px rgba(245, 158, 11, 0.6)',
          }}
        >
          <Trophy size={isProjectorMode ? 48 : 38} />
        </div>

        <div className="badge badge-amber results-champion-label" style={{ marginBottom: '12px', fontSize: '0.85rem', padding: '6px 14px' }}>
          ĐỘI VÔ ĐỊCH CHIẾN DỊCH TEAM-BUILDING
        </div>

        <h1
          className="results-winner-name"
          style={{
            fontSize: isProjectorMode ? '3.5rem' : '2.6rem',
            fontWeight: 900,
            margin: '0 0 10px 0',
            letterSpacing: '0.5px',
            background: 'linear-gradient(135deg, #ffffff 40%, #fde68a 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          {winnerName.toUpperCase()}
        </h1>

        <p
          style={{
            color: 'var(--text-muted)',
            fontSize: isProjectorMode ? '1.3rem' : '1.05rem',
            maxWidth: '680px',
            margin: '0 auto',
            lineHeight: 1.6,
          }}
        >
          Chiến thắng áp đảo với chiến lược phòng thủ kiên cố, khả năng hiệp đồng tác chiến và kiến thức chuyên môn xuất sắc!
        </p>
      </div>

      {/* 2. Official Final Standings Leaderboard Table (§14.9, §13 FR-10) */}
      <div className="glass-panel results-standings" style={{ padding: isProjectorMode ? '36px' : '28px', marginBottom: '36px' }}>
        <div className="results-section-heading" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3
            style={{
              fontSize: isProjectorMode ? '1.6rem' : '1.3rem',
              fontWeight: 800,
              margin: 0,
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}
          >
            <Award size={24} style={{ color: 'var(--accent-cyan)' }} />
            Bảng Xếp Hạng Chung Cuộc & Phân Tích Điểm Số (Official Standings)
          </h3>
          <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
            Tie-break: Điểm số &gt; Căn cứ phá &gt; Máu căn cứ &gt; Coin còn lại
          </span>
        </div>

        <div className="results-table-scroll" style={{ overflow: 'auto', maxHeight: '65vh' }}>
          <table
            className="results-table"
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              textAlign: 'left',
              fontSize: isProjectorMode ? '1.15rem' : '0.92rem',
            }}
          >
            <thead>
              <tr
                style={{
                  borderBottom: '2px solid var(--border-subtle)',
                  color: 'var(--text-dim)',
                  fontSize: isProjectorMode ? '0.9rem' : '0.8rem',
                  textTransform: 'uppercase',
                }}
              >
                <th style={{ padding: isProjectorMode ? '16px' : '12px' }}>HẠNG</th>
                <th style={{ padding: isProjectorMode ? '16px' : '12px' }}>TÊN ĐỘI HÌNH</th>
                <th style={{ padding: isProjectorMode ? '16px' : '12px', textAlign: 'center' }}>TỔNG ĐIỂM</th>
                <th style={{ padding: isProjectorMode ? '16px' : '12px' }}>CĂN CỨ ĐÃ PHÁ</th>
                <th style={{ padding: isProjectorMode ? '16px' : '12px' }}>SÁT THƯƠNG</th>
                <th style={{ padding: isProjectorMode ? '16px' : '12px' }}>MÁU CÒN LẠI</th>
                <th style={{ padding: isProjectorMode ? '16px' : '12px' }}>CÂU ĐÚNG</th>
                <th style={{ padding: isProjectorMode ? '16px' : '12px' }}>THÁP SỐNG</th>
              </tr>
            </thead>
            <tbody>
              {resultsList.map((team, index) => {
                const isEliminated = team.remaining_base_hp <= 0;
                const isFirst = index === 0;
                return (
                  <tr
                    key={team.team_id || team.team_name}
                    className={isFirst ? 'is-champion' : ''}
                    style={{
                      borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                      background: isFirst ? 'rgba(245, 158, 11, 0.06)' : undefined,
                    }}
                  >
                    {/* Rank */}
                    <td style={{ padding: isProjectorMode ? '20px 16px' : '16px 12px', fontWeight: 800 }}>
                      <span
                        className={`results-rank rank-${team.final_rank}`}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: isProjectorMode ? '36px' : '28px',
                          height: isProjectorMode ? '36px' : '28px',
                          borderRadius: '50%',
                          background:
                            index === 0
                              ? 'linear-gradient(135deg, #f59e0b, #d97706)'
                              : index === 1
                              ? 'linear-gradient(135deg, #94a3b8, #64748b)'
                              : index === 2
                              ? 'linear-gradient(135deg, #b45309, #78350f)'
                              : 'rgba(255, 255, 255, 0.1)',
                          color: index < 3 ? '#0f172a' : 'var(--text-dim)',
                          fontSize: isProjectorMode ? '1.1rem' : '0.85rem',
                        }}
                      >
                        #{team.final_rank}
                      </span>
                    </td>

                    {/* Team Name */}
                    <td style={{ padding: isProjectorMode ? '20px 16px' : '16px 12px' }}>
                      <div style={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span>{team.team_name}</span>
                        {isEliminated && (
                          <span className="badge badge-rose" style={{ fontSize: '0.7rem' }}>
                            Đã bị loại
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Final Score */}
                    <td
                      className="results-score"
                      style={{
                        padding: isProjectorMode ? '20px 16px' : '16px 12px',
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 900,
                        color: 'var(--accent-cyan)',
                        fontSize: isProjectorMode ? '1.5rem' : '1.25rem',
                        textAlign: 'center',
                      }}
                    >
                      {team.final_score}
                    </td>

                    {/* Bases Destroyed */}
                    <td style={{ padding: isProjectorMode ? '20px 16px' : '16px 12px' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Swords size={15} style={{ color: 'var(--accent-rose)' }} />
                        <strong>{team.bases_destroyed}</strong> căn cứ
                      </span>
                    </td>

                    {/* Damage */}
                    <td style={{ padding: isProjectorMode ? '20px 16px' : '16px 12px', fontFamily: 'var(--font-mono)' }}>
                      {team.base_damage_dealt} DMG
                    </td>

                    {/* Remaining HP */}
                    <td style={{ padding: isProjectorMode ? '20px 16px' : '16px 12px' }}>
                      <span
                        style={{
                          color: isEliminated ? 'var(--accent-rose)' : 'var(--accent-emerald)',
                          fontWeight: 700,
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        {team.remaining_base_hp} HP
                      </span>
                    </td>

                    {/* Correct Answers */}
                    <td style={{ padding: isProjectorMode ? '20px 16px' : '16px 12px' }}>
                      <span className="badge badge-purple" style={{ fontSize: '0.82rem' }}>
                        {team.correct_answers} câu
                      </span>
                    </td>

                    {/* Surviving Towers */}
                    <td style={{ padding: isProjectorMode ? '20px 16px' : '16px 12px' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Castle size={14} style={{ color: 'var(--accent-cyan)' }} />
                        {team.surviving_towers}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. Optional Awards Badges (§14.9, §33, D14) */}
      <div className="results-awards" style={{ marginBottom: '36px' }}>
        <div className="results-section-heading results-awards-heading" style={{ marginBottom: '18px' }}>
          <h3
            style={{
              fontSize: isProjectorMode ? '1.6rem' : '1.3rem',
              fontWeight: 800,
              margin: '0 0 6px 0',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}
          >
            <Sparkles size={24} style={{ color: 'var(--accent-amber)' }} />
            Danh Hiệu Vinh Danh Tác Chiến (Optional Awards)
          </h3>
          <p style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-muted)' }}>
            Tôn vinh các khía cạnh đặc biệt của tinh thần đồng đội mà không làm sai lệch bảng điểm chính thức (Quy ước D14).
          </p>
        </div>

        <div
          className="results-award-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: isProjectorMode ? 'repeat(5, 1fr)' : 'repeat(auto-fit, minmax(210px, 1fr))',
            gap: '16px',
          }}
        >
          {awardsList.map((award) => (
            <div
              key={award.id}
              className="glass-panel"
              data-award-card
              style={{
                padding: '20px 16px',
                textAlign: 'center',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                borderTop: '3px solid var(--accent-amber)',
              }}
            >
              <div>
                <div
                  className="results-award-seal"
                  style={{
                    width: '44px',
                    height: '44px',
                    borderRadius: '50%',
                    background: 'rgba(255, 255, 255, 0.05)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: '10px',
                  }}
                >
                  {getAwardIcon(award.id)}
                </div>
                <h4 className="results-award-name" style={{ fontSize: '0.95rem', fontWeight: 800, margin: '0 0 6px 0' }}>{award.name}</h4>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.4, margin: '0 0 12px 0' }}>
                  {award.description}
                </p>
              </div>

              <div
                className="results-award-recipient"
                style={{
                  background: 'rgba(245, 158, 11, 0.1)',
                  borderRadius: '6px',
                  padding: '8px 10px',
                  border: '1px solid rgba(245, 158, 11, 0.25)',
                }}
              >
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>Vinh danh</div>
                <div style={{ fontWeight: 800, color: 'var(--accent-amber)', fontSize: '0.92rem', marginTop: '2px' }}>
                  {award.team_name}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 4. Action & Navigation Footer */}
      {!isProjectorMode && (
        <div className="results-footer-actions" style={{ display: 'flex', gap: '14px', justifyContent: 'center', flexWrap: 'wrap' }}>
          <Link to="/" className="btn-secondary" style={{ padding: '12px 24px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Home size={18} /> Về Trang Chủ
          </Link>

          {matchId && (
            <button
              onClick={handleRematch}
              disabled={rematchLoading}
              className="btn-primary"
              style={{ padding: '12px 28px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.95rem' }}
            >
              <RotateCcw size={18} /> {rematchLoading ? 'Đang chuẩn bị...' : 'Tổ Chức Trận Tái Đấu (Rematch)'}
            </button>
          )}

          <Link
            to={matchId ? `/lobby/${matchId}?host=1` : '/join'}
            className="btn-secondary"
            style={{ padding: '12px 24px', display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            <RotateCcw size={18} /> Tham Gia Phòng Mới
          </Link>
        </div>
      )}
    </div>
  );
};
