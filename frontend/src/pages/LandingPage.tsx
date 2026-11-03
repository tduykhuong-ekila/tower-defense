import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  BookOpen,
  CheckCircle2,
  Crosshair,
  HelpCircle,
  Play,
  Plus,
  Shield,
  Swords,
  Users,
  X,
} from 'lucide-react';
import { api, setHostToken } from '../services/api';
import { Match } from '../types/match';
import { MaximumTeamsSelect, useRoomConstraints } from '../components/MaximumTeamsSelect';
import { QuestionBankUpload } from '../components/QuestionBankUpload';
import { StagedQuestionBank } from '../types/questionBank';
import { entityArtwork } from '../game/entityArtwork';
import './LandingPage.css';

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const [backendStatus, setBackendStatus] = useState<string>('đang kiểm tra...');
  const [isHealthy, setIsHealthy] = useState<boolean>(false);
  const [activeMatches, setActiveMatches] = useState<Match[]>([]);
  const [roomCodeInput, setRoomCodeInput] = useState<string>('');

  // Modals
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [showRulesModal, setShowRulesModal] = useState<boolean>(false);

  // Create match form
  const [createName, setCreateName] = useState<string>('Đại Chiến Đấu Trường');
  const { constraints, error: constraintsError } = useRoomConstraints();
  const [maxTeams, setMaxTeams] = useState<number>();
  const [totalRounds, setTotalRounds] = useState<2 | 3>(3);
  const [prepSeconds, setPrepSeconds] = useState(180);
  const [battleSeconds, setBattleSeconds] = useState(300);
  const [initialHp, setInitialHp] = useState<number>(500);
  const [initialCoins, setInitialCoins] = useState<number>(100);
  const [isCreating, setIsCreating] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [questionBank, setQuestionBank] = useState<StagedQuestionBank | null>(null);
  const [bankReady, setBankReady] = useState(true);
  const creationToken = useRef(crypto.randomUUID());
  const createLock = useRef(false);

  useEffect(() => {
    api.getHealth()
      .then((res) => {
        setBackendStatus(res.status === 'healthy' ? 'hoạt động' : res.status);
        setIsHealthy(res.status === 'healthy');
      })
      .catch(() => {
        setBackendStatus('mất kết nối');
        setIsHealthy(false);
      });

    api.listMatches()
      .then((res) => {
        setActiveMatches(res);
      })
      .catch(() => {
        setActiveMatches([]);
      });
  }, []);

  const handleQuickJoin = (e: React.FormEvent) => {
    e.preventDefault();
    if (roomCodeInput.trim()) {
      navigate(`/join?code=${roomCodeInput.trim().toUpperCase()}`);
    }
  };

  const handleCreateMatch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!constraints || !bankReady || createLock.current) return;
    createLock.current = true;
    setIsCreating(true);
    setCreateError(null);

    try {
      const match = await api.createMatch({
        name: createName,
        creation_token: creationToken.current,
        ...(questionBank ? { question_bank_id: questionBank.id, question_bank_token: questionBank.token } : {}),
        configuration: {
          max_teams: maxTeams ?? constraints.default_max_teams,
          gameplay_mode: "CONTINUOUS",
          total_rounds: totalRounds,
          preparation_duration_seconds: prepSeconds,
          first_preparation_duration_seconds: prepSeconds === 180 ? 120 : prepSeconds,
          battle_duration_seconds: battleSeconds,
          initial_base_hp: initialHp,
          initial_coins: initialCoins,
        },
      });

      if (match.host_token) {
        setHostToken(match.host_token);
      }
      setShowCreateModal(false);
      navigate(`/lobby/${match.id}?host=1`);
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : 'Tạo phòng thất bại');
    } finally {
      createLock.current = false;
      setIsCreating(false);
    }
  };

  return (
    <div className="landing-page">
      <section className="landing-hero">
        <div className="landing-hero-copy">
          <div className="landing-eyebrow"><span className="landing-eyebrow-mark"><Shield size={14} /></span> ĐẤU TRƯỜNG CHIẾN THUẬT ĐỒNG ĐỘI</div>
          <h1>GIỮ VỮNG<br /><span>PHÒNG TUYẾN</span></h1>
          <p className="landing-intro">
            Cùng đồng đội giải mã thử thách, xây tháp canh và đưa đạo quân băng qua rừng sâu. Mỗi câu trả lời đúng có thể xoay chuyển cả chiến trường.
          </p>

          <div className="landing-actions">
            <button
              onClick={() => { setQuestionBank(null); setBankReady(true); creationToken.current = crypto.randomUUID(); setCreateError(null); setShowCreateModal(true); }}
              className="btn-primary landing-create-button"
            >
              <Plus size={18} /> Dựng phòng tuyến
            </button>
            <button onClick={() => setShowRulesModal(true)} className="landing-rules-button">
              <BookOpen size={17} /> Xem luật chơi
            </button>
          </div>

          <form onSubmit={handleQuickJoin} className="landing-join-card">
            <div className="landing-join-icon"><Play size={16} fill="currentColor" /></div>
            <label htmlFor="landing-room-code">
              <span>ĐÃ CÓ MÃ PHÒNG?</span>
              <input
                id="landing-room-code"
                type="text"
                maxLength={6}
                value={roomCodeInput}
                onChange={(e) => setRoomCodeInput(e.target.value.toUpperCase())}
                placeholder="NHẬP MÃ 6 KÝ TỰ"
                autoComplete="off"
              />
            </label>
            <button type="submit" aria-label="Vào phòng đấu"><Play size={18} /></button>
          </form>

          <div className="landing-server-status">
            <span className={`landing-status-dot${isHealthy ? ' is-online' : ''}`} />
            <Activity size={14} /> Máy chủ <strong>{backendStatus}</strong>
          </div>
        </div>

        <div className="landing-map-wrap" aria-label="Minh họa chiến trường rừng xanh">
          <div className="landing-map-frame">
            <div className="landing-map-topline"><span><Crosshair size={13} /> CHIẾN TRƯỜNG</span><span>KHU RỪNG PHÍA BẮC · 01</span></div>
            <div className="landing-map-scene">
              <div className="landing-map-haze" />
              <svg className="landing-map-routes" viewBox="0 0 640 420" preserveAspectRatio="none" aria-hidden="true">
                <path className="landing-river-edge" d="M-25 328 C116 247 155 368 274 280 S456 188 670 246" />
                <path className="landing-river" d="M-25 328 C116 247 155 368 274 280 S456 188 670 246" />
                <path className="landing-road-shadow" d="M72 357 C154 289 210 247 298 213 S450 173 584 74" />
                <path className="landing-road" d="M72 357 C154 289 210 247 298 213 S450 173 584 74" />
                <path className="landing-road-mark" d="M72 357 C154 289 210 247 298 213 S450 173 584 74" />
              </svg>
              <img className="landing-tree tree-a" src="/assets/woodland/tree-0.svg" alt="" />
              <img className="landing-tree tree-b" src="/assets/woodland/tree-1.svg" alt="" />
              <img className="landing-tree tree-c" src="/assets/woodland/tree-2.svg" alt="" />
              <img className="landing-tree tree-d" src="/assets/woodland/tree-0.svg" alt="" />
              <img className="landing-tower-art" src={entityArtwork('cannon_tower')} alt="" />
              <img className="landing-tank-art" src={entityArtwork('tank')} alt="" />
              <img className="landing-base-art" src="/assets/woodland/base-0.svg" alt="" />
              <span className="landing-map-marker marker-one"><i /> CĂN CỨ</span>
              <span className="landing-map-marker marker-two"><i /> TUYẾN PHÒNG THỦ</span>
              <span className="landing-map-coords">N 04° · E 12°</span>
              <div className="landing-map-callout"><span className="landing-callout-icon"><Swords size={16} /></span><span><b>ĐỒNG ĐỘI, XUẤT KÍCH!</b><small>CHIẾN THUẬT · KIẾN THỨC · PHỐI HỢP</small></span></div>
            </div>
            <div className="landing-map-footer"><span><span className="landing-live-dot" /> TRẬN ĐẤU THỜI GIAN THỰC</span><span><Users size={13} /> 2–20 ĐỘI</span></div>
          </div>
          <div className="landing-map-seal"><Shield size={22} /><span>THỦ<br />THÀNH</span></div>
        </div>
      </section>

      {/* Active Lobby Rooms (if any) */}
      {activeMatches.length > 0 && (
        <div className="landing-rooms">
          <div className="landing-section-heading">
            <div><span className="landing-section-kicker">GỌI ĐỒNG ĐỘI</span><h2><Users size={20} /> Phòng chờ đang mở <span>{activeMatches.length}</span></h2></div>
            <span>Chọn một phòng để tham chiến</span>
          </div>

          <div className="landing-room-grid">
            {activeMatches.map((m) => (
              <div key={m.id} className="landing-room-card">
                <div className="landing-room-crest"><Shield size={19} /></div>
                <div className="landing-room-info">
                  <strong>{m.name}</strong>
                  <span><b>#{m.room_code}</b><i />{m.teams?.length || 0} đội<i /><em>{m.phase}</em></span>
                </div>
                <button onClick={() => navigate(`/join?code=${m.room_code}`)} className="landing-room-join">Tham gia <Play size={13} fill="currentColor" /></button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pillars Section */}
      <section className="landing-pillars">
        <div className="landing-section-heading landing-pillars-heading">
          <div><span className="landing-section-kicker">CÁCH CHƠI</span><h2>Ba mũi nhọn chiến thắng</h2></div>
          <span>Đoàn kết để bảo vệ căn cứ</span>
        </div>
        <div className="landing-pillar-grid">
        <div className="landing-pillar-card">
          <div className="landing-pillar-icon knowledge"><HelpCircle size={23} /></div>
          <div className="landing-pillar-number">01 / TRI THỨC</div>
          <h3>Giải mã thử thách</h3>
          <p>
            Phối hợp nhịp nhàng giữa Mentor và Mentee để giải quyết câu hỏi thuật toán, giải mã dữ liệu và thu về lợi thế chiến lược vượt trội.
          </p>
        </div>

        <div className="landing-pillar-card">
          <div className="landing-pillar-icon resources"><Users size={23} /></div>
          <div className="landing-pillar-number">02 / TÀI NGUYÊN</div>
          <h3>Xây quân, giữ đất</h3>
          <p>
            Đưa ra quyết định then chốt: thu về dòng tiền coin ngay lập tức hoặc mở khóa vĩnh viễn Xe Tăng hạng nặng, Pháo Binh và Máy Tạo Khiên.
          </p>
        </div>

        <div className="landing-pillar-card">
          <div className="landing-pillar-icon battle"><Swords size={23} /></div>
          <div className="landing-pillar-number">03 / ĐỒNG ĐỘI</div>
          <h3>Phản công đúng lúc</h3>
          <p>
            Hệ thống giải quyết giao tranh theo lượt tất định trên làn đường cố định, ưu tiên mục tiêu thông minh và chiến thắng theo tiêu chí triệt hạ căn cứ.
          </p>
        </div>
        </div>
      </section>

      {/* CREATE MATCH MODAL */}
      {showCreateModal && (
        <div
          className="landing-modal-backdrop"
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
          <div className="glass-panel landing-modal-card" style={{ width: '100%', maxWidth: '640px', maxHeight: '90vh', overflowY: 'auto', padding: '36px', position: 'relative' }}>
            <button
              onClick={() => setShowCreateModal(false)}
              style={{
                position: 'absolute',
                right: '20px',
                top: '20px',
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                cursor: 'pointer',
              }}
            >
              <X size={20} />
            </button>

            <h2 style={{ fontSize: '1.6rem', fontWeight: 800, marginBottom: '6px' }}>Cấu hình trận đấu mới</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '24px' }}>
              Khởi tạo phòng đấu chính thức. Bạn sẽ nhận được mã bảo mật độc quyền của Quản trị viên (Host).
            </p>

            {createError && (
              <div
                style={{
                  background: 'rgba(244, 63, 94, 0.15)',
                  border: '1px solid rgba(244, 63, 94, 0.3)',
                  color: 'var(--accent-rose)',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  marginBottom: '16px',
                  fontSize: '0.85rem',
                }}
              >
                {createError}
              </div>
            )}

            <form onSubmit={handleCreateMatch}>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                  TÊN TRẬN ĐẤU
                </label>
                <input
                  type="text"
                  required
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
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

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '16px' }}>
                <MaximumTeamsSelect value={maxTeams} onChange={setMaxTeams}
                  constraints={constraints} error={constraintsError} />

                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                    MÁU CĂN CỨ KHỞI ĐIỂM
                  </label>
                  <input
                    type="number"
                    min={100}
                    max={2000}
                    step={50}
                    value={initialHp}
                    onChange={(e) => setInitialHp(Number(e.target.value))}
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

              <fieldset style={{ marginBottom: 20, display: 'flex', flexWrap: 'wrap', gap: 16, padding: 14 }}>
                <legend>Nhịp trận đấu</legend>
                <label>Số vòng chính <select aria-label="Số vòng chính" value={totalRounds} onChange={e => setTotalRounds(Number(e.target.value) as 2 | 3)}><option value={2}>2 vòng</option><option value={3}>3 vòng</option></select></label>
                <label>Chuẩn bị giữa vòng (giây) <input aria-label="Thời gian chuẩn bị" type="number" min={1} max={900} value={prepSeconds} onChange={e => setPrepSeconds(Number(e.target.value))} style={{width:80}} /></label>
                <label>Giao tranh (giây) <input aria-label="Thời gian giao tranh" type="number" min={1} max={1800} value={battleSeconds} onChange={e => setBattleSeconds(Number(e.target.value))} style={{width:80}} /></label>
                <small>Mặc định: chuẩn bị vòng đầu 2 phút, giữa các vòng 3 phút. Quân và công sự được giữ qua các vòng.</small>
              </fieldset>
              <div style={{ marginBottom: '24px' }}>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                  SỐ COIN KHỞI ĐIỂM MỖI ĐỘI
                </label>
                <input
                  type="number"
                  min={50}
                  max={500}
                  step={25}
                  value={initialCoins}
                  onChange={(e) => setInitialCoins(Number(e.target.value))}
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

              <QuestionBankUpload disabled={isCreating} onChange={(bank, ready) => { setQuestionBank(bank); setBankReady(ready); }} />

              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="btn-secondary"
                  style={{ padding: '10px 20px' }}
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={isCreating || !constraints || !bankReady}
                  className="btn-primary"
                  style={{ padding: '10px 24px' }}
                >
                  {isCreating ? 'Đang tạo phòng...' : 'Khởi tạo phòng chờ'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* HOW TO PLAY MODAL */}
      {showRulesModal && (
        <div
          className="landing-modal-backdrop"
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
          <div
            className="glass-panel landing-modal-card"
            style={{
              width: '100%',
              maxWidth: '680px',
              maxHeight: '85vh',
              overflowY: 'auto',
              padding: '36px',
              position: 'relative',
            }}
          >
            <button
              onClick={() => setShowRulesModal(false)}
              style={{
                position: 'absolute',
                right: '20px',
                top: '20px',
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                cursor: 'pointer',
              }}
            >
              <X size={20} />
            </button>

            <h2 style={{ fontSize: '1.6rem', fontWeight: 800, marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <BookOpen size={24} style={{ color: 'var(--accent-cyan)' }} /> Hướng dẫn Luật chơi & Kiến trúc Trận đấu
            </h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '24px' }}>
              Trích xuất quy tắc chuẩn hóa từ GDD_PRD §4, §11, §12.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px', fontSize: '0.92rem', lineHeight: 1.6 }}>
              <div>
                <h4 style={{ color: 'var(--accent-cyan)', fontWeight: 700, marginBottom: '6px' }}>1. Cơ cấu Đội hình & Vai trò</h4>
                <p style={{ color: 'var(--text-muted)' }}>
                  Mỗi đội gồm <strong>1 Mentor (Cố vấn kỹ thuật)</strong> và <strong>1 đến 3 Mentee (Chiến binh tác chiến)</strong>.
                  Mentor tư vấn chiến thuật giải đố và phân bổ nguồn lực, Mentee trực tiếp trả lời câu hỏi và điều phối đơn vị.
                </p>
              </div>

              <div>
                <h4 style={{ color: 'var(--accent-amber)', fontWeight: 700, marginBottom: '6px' }}>2. Chuỗi 5 Giai đoạn trận đấu</h4>
                <ul style={{ paddingLeft: '20px', color: 'var(--text-muted)' }}>
                  <li><strong>Chuẩn bị (Preparation - 3 phút):</strong> Thảo luận chiến lược ban đầu và do thám bản đồ căn cứ đối thủ.</li>
                  <li><strong>Xây dựng & Do thám (Build & Scout - 7 phút):</strong> Trả lời câu hỏi để kiếm coin hoặc mở khóa đơn vị. Dựng tháp phòng thủ.</li>
                  <li><strong>Chiến tranh (War - 12 phút):</strong> Giao tranh cường độ cao, xuất kích quân và tấn công căn cứ đối phương.</li>
                  <li><strong>Tổng công kích (Final Assault - 5 phút):</strong> Đợt tấn công quyết định cuối cùng nhằm triệt tiêu các căn cứ còn sống sót.</li>
                  <li><strong>Tổng kết kết quả (Results - 3 phút):</strong> Hệ thống tính điểm tác chiến, trao huy hiệu và công bố xếp hạng.</li>
                </ul>
              </div>

              <div>
                <h4 style={{ color: 'var(--accent-emerald)', fontWeight: 700, marginBottom: '6px' }}>3. Lựa chọn Phần thưởng Kinh tế</h4>
                <p style={{ color: 'var(--text-muted)' }}>
                  Khi trả lời đúng một câu hỏi, đội được quyền chọn giữa <strong>mở túi coin bí ẩn (20–60 coin ngẫu nhiên)</strong> hoặc <strong>mở khóa vĩnh viễn đơn vị</strong> (Xe tăng, Pháo binh, Khiên phòng hộ).
                </p>
              </div>

              <div>
                <h4 style={{ color: 'var(--accent-rose)', fontWeight: 700, marginBottom: '6px' }}>4. Điều kiện Chiến thắng</h4>
                <p style={{ color: 'var(--text-muted)' }}>
                  <strong>Chiến thắng Triệt hạ:</strong> Căn cứ cuối cùng còn sống sẽ giành chiến thắng ngay lập tức.<br />
                  <strong>Chiến thắng Điểm số:</strong> Khi hết giờ, đội có điểm cao nhất sẽ chiến thắng (phá hủy căn cứ địch +100 điểm, sát thương gây ra, máu căn cứ còn lại và số tháp bảo tồn).
                </p>
              </div>
            </div>

            <div style={{ marginTop: '28px', textAlign: 'right' }}>
              <button onClick={() => setShowRulesModal(false)} className="btn-primary" style={{ padding: '10px 24px' }}>
                <CheckCircle2 size={16} /> Đã hiểu, sẵn sàng tham chiến
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
