import React, { useState } from "react";
import { Swords, Shield, Zap, Skull, Trophy, Play } from "lucide-react";
import { api } from "../../services/api";
import { CombatEvent, RoundResult } from "../../types/combat";

interface CombatDebugViewerProps {
  matchId: string;
  isHost?: boolean;
  onRoundResolved?: (result: RoundResult) => void;
}

export const CombatDebugViewer: React.FC<CombatDebugViewerProps> = ({
  matchId,
  isHost = true,
  onRoundResolved,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRoundResult, setLastRoundResult] = useState<RoundResult | null>(
    null,
  );
  const [roundHistory, setRoundHistory] = useState<RoundResult[]>([]);

  const handleResolveRound = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.resolveCombat(matchId);
      setLastRoundResult(result);
      setRoundHistory((prev) => [result, ...prev]);
      if (onRoundResolved) {
        onRoundResolved(result);
      }
    } catch (err: any) {
      setError(err.message || "Lỗi khi kích hoạt tính toán round chiến đấu.");
    } finally {
      setLoading(false);
    }
  };

  const getEventBadge = (type: string) => {
    switch (type) {
      case "TOWER_ATTACKED":
        return (
          <span
            className="badge badge-amber"
            style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}
          >
            <Zap size={12} /> THÁP BẮN
          </span>
        );
      case "UNIT_ATTACKED":
        return (
          <span
            className="badge badge-rose"
            style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}
          >
            <Swords size={12} /> LÍNH GIAO TRANH
          </span>
        );
      case "BASE_DAMAGED":
        return (
          <span
            className="badge badge-purple"
            style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}
          >
            <Skull size={12} /> BẮN CĂN CỨ
          </span>
        );
      case "UNIT_MOVED":
        return (
          <span
            className="badge badge-cyan"
            style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}
          >
            DI CHUYỂN
          </span>
        );
      case "SHIELD_GENERATED":
        return (
          <span
            className="badge badge-emerald"
            style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}
          >
            <Shield size={12} /> TẠO KHIÊN
          </span>
        );
      case "TEAM_ELIMINATED":
      case "BASE_DESTROYED":
        return (
          <span
            className="badge badge-rose"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              background: "rgba(239, 68, 68, 0.3)",
            }}
          >
            <Skull size={12} /> BỊ TRIỆT HẠ
          </span>
        );
      case "VICTORY_DECLARED":
        return (
          <span
            className="badge badge-amber"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              fontWeight: 800,
            }}
          >
            <Trophy size={12} /> CHIẾN THẮNG
          </span>
        );
      case "INCOME_AWARDED":
        return (
          <span
            className="badge badge-emerald"
            style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}
          >
            + THU NHẬP
          </span>
        );
      default:
        return <span className="badge badge-gray">{type}</span>;
    }
  };

  return (
    <div className="glass-panel" style={{ padding: "24px", marginTop: "24px" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "16px",
        }}
      >
        <div>
          <h3
            style={{
              fontSize: "1.15rem",
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <Swords size={20} style={{ color: "var(--accent-amber)" }} />
            Điều khiển giao tranh
          </h3>
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
            Bắt đầu vòng tiếp theo và gửi diễn biến chiến đấu đến tất cả các
            đội.
          </p>
        </div>

        {isHost && (
          <button
            onClick={handleResolveRound}
            disabled={loading}
            className="btn-primary"
            style={{
              padding: "10px 20px",
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              fontWeight: 700,
            }}
          >
            <Play size={16} />
            {loading ? "Đang tính toán..." : "Bắt đầu vòng tiếp theo"}
          </button>
        )}
      </div>

      {error && (
        <div
          style={{
            padding: "12px 16px",
            background: "rgba(239, 68, 68, 0.15)",
            border: "1px solid var(--accent-rose)",
            borderRadius: "8px",
            color: "var(--accent-rose)",
            fontSize: "0.9rem",
            marginBottom: "16px",
          }}
        >
          {error}
        </div>
      )}

      {lastRoundResult && (
        <div
          style={{
            marginBottom: "20px",
            padding: "16px",
            background: "rgba(255, 255, 255, 0.03)",
            borderRadius: "8px",
            border: "1px solid var(--border-subtle)",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "12px",
            }}
          >
            <span
              style={{
                fontWeight: 800,
                color: "var(--accent-cyan)",
                fontSize: "1rem",
              }}
            >
              Round #{lastRoundResult.round_number} Đã Hoàn Tất
            </span>
            <div style={{ display: "flex", gap: "8px" }}>
              <span className="badge badge-gray">
                {lastRoundResult.events.length} Sự kiện
              </span>
              {lastRoundResult.is_match_over && (
                <span
                  className="badge badge-amber"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "4px",
                  }}
                >
                  <Trophy size={12} /> Trận Đấu Kết Thúc
                </span>
              )}
            </div>
          </div>

          <div style={{ maxHeight: "280px", overflowY: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "0.85rem",
                textAlign: "left",
              }}
            >
              <thead>
                <tr
                  style={{
                    borderBottom: "1px solid var(--border-subtle)",
                    color: "var(--text-dim)",
                  }}
                >
                  <th style={{ padding: "8px" }}>LOẠI SỰ KIỆN</th>
                  <th style={{ padding: "8px" }}>CHI TIẾT</th>
                  <th style={{ padding: "8px" }}>SÁT THƯƠNG / HIỆU ỨNG</th>
                </tr>
              </thead>
              <tbody>
                {lastRoundResult.events.map((ev: CombatEvent, i: number) => (
                  <tr
                    key={i}
                    style={{
                      borderBottom: "1px solid rgba(255, 255, 255, 0.03)",
                    }}
                  >
                    <td style={{ padding: "8px" }}>{getEventBadge(ev.type)}</td>
                    <td
                      style={{ padding: "8px", color: "var(--text-secondary)" }}
                    >
                      {ev.type === "UNIT_MOVED" &&
                        `Đơn vị ${ev.entity_id?.slice(0, 8)}: ${ev.from_node} ➔ ${ev.to_node}`}
                      {ev.type === "TOWER_ATTACKED" &&
                        `Tháp ${ev.tower_id?.slice(0, 8)} nhắm bắn đơn vị ${ev.target_entity_id?.slice(0, 8)}`}
                      {ev.type === "UNIT_ATTACKED" &&
                        `Lính ${ev.attacker_id?.slice(0, 8)} tấn công lính ${ev.target_entity_id?.slice(0, 8)}`}
                      {ev.type === "BASE_DAMAGED" &&
                        `Căn cứ ${ev.target_team_id?.slice(0, 8)} trúng đòn từ ${ev.unit_id?.slice(0, 8)}`}
                      {ev.type === "ENTITY_DESTROYED" &&
                        `Đơn vị ${ev.entity_id?.slice(0, 8)} bị tiêu diệt (${ev.reason})`}
                      {ev.type === "INCOME_AWARDED" &&
                        `Đội ${ev.team_id?.slice(0, 8)} nhận +${ev.amount} coin`}
                      {ev.type === "SHIELD_GENERATED" &&
                        `Đội ${ev.team_id?.slice(0, 8)} kích hoạt khiên +${ev.shield_amount} HP`}
                      {ev.type === "TEAM_ELIMINATED" &&
                        `Đội ${ev.team_name || ev.team_id?.slice(0, 8)} BỊ LOẠI KHỎI TRẬN ĐẤU`}
                      {ev.type === "VICTORY_DECLARED" &&
                        `Người chiến thắng: ${ev.winner_team_id || "Đồng hạng theo điểm"}`}
                      {ev.type === "COMBAT_RESOLVED" &&
                        `Round ${ev.round_number} Authoritative State Broadcast`}
                    </td>
                    <td
                      style={{ padding: "8px", fontFamily: "var(--font-mono)" }}
                    >
                      {ev.damage && (
                        <span style={{ color: "var(--accent-rose)" }}>
                          -{ev.damage} DMG{" "}
                        </span>
                      )}
                      {ev.shield_absorbed ? (
                        <span style={{ color: "var(--accent-cyan)" }}>
                          ({ev.shield_absorbed} khiên){" "}
                        </span>
                      ) : null}
                      {ev.base_hp_remaining !== undefined && (
                        <span style={{ color: "var(--text-muted)" }}>
                          Căn cứ còn: {ev.base_hp_remaining} HP
                        </span>
                      )}
                      {ev.new_balance !== undefined && (
                        <span style={{ color: "var(--accent-emerald)" }}>
                          Số dư: {ev.new_balance} coin
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {roundHistory.length > 1 && (
        <div style={{ marginTop: "16px" }}>
          <h4
            style={{
              fontSize: "0.9rem",
              color: "var(--text-dim)",
              marginBottom: "8px",
            }}
          >
            Lịch Sử Các Round Trước ({roundHistory.length})
          </h4>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            {roundHistory.map((rh) => (
              <button
                key={rh.round_number}
                onClick={() => setLastRoundResult(rh)}
                className={`btn-secondary ${lastRoundResult?.round_number === rh.round_number ? "btn-active" : ""}`}
                style={{ padding: "4px 12px", fontSize: "0.8rem" }}
              >
                Round #{rh.round_number} ({rh.events.length} evs)
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
