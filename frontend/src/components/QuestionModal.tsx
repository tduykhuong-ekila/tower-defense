import React, { useState, useEffect, useRef } from "react";
import {
  HelpCircle,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ArrowRight,
  Send,
  Loader2,
  X,
} from "lucide-react";
import { useModalFocus } from "./useModalFocus";
import { TeamQuestion } from "../types/question";
import { RewardOptions } from "../types/reward";

interface QuestionModalProps {
  isOpen: boolean;
  questionState: TeamQuestion | null;
  onSubmitAnswer: (answer: string) => Promise<TeamQuestion>;
  onRewardTrigger: (
    rewardOptions: RewardOptions,
    teamQuestionId: string,
  ) => void;
  onClose: () => void;
  onNextQuestion?: () => Promise<void>;
  isSubmitting?: boolean;
  totalQuestions?: number;
  matchEnded?: boolean;
}

export const QuestionModal: React.FC<QuestionModalProps> = ({
  isOpen,
  questionState,
  onSubmitAnswer,
  onRewardTrigger,
  onClose,
  onNextQuestion,
  isSubmitting = false,
  totalQuestions,
  matchEnded = false,
}) => {
  const dialog = useRef<HTMLDivElement>(null);
  useModalFocus(isOpen && !!questionState, dialog, onClose);
  const [selectedOption, setSelectedOption] = useState<string>("");
  const [textAnswer, setTextAnswer] = useState<string>("");
  const [secondsRemaining, setSecondsRemaining] = useState<number>(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isLoadingNext, setIsLoadingNext] = useState(false);

  // Draft lifetime follows the question identity, independent of visibility/timer updates.
  useEffect(() => {
    setSelectedOption("");
    setTextAnswer("");
    setErrorMsg(null);
  }, [questionState?.id]);

  useEffect(() => {
    if (!isOpen || !questionState) return;
    const receivedAt = performance.now();
    const initial = questionState.timer?.remaining_ms ?? questionState.time_remaining_seconds * 1000;
    const running = questionState.status === "PENDING_QUESTION" && questionState.timer?.status === "RUNNING";
    const updateTimer = () => setSecondsRemaining(Math.max(0,
      Math.ceil((initial - (running ? performance.now() - receivedAt : 0)) / 1000)));
    updateTimer();
    const interval = setInterval(updateTimer, 250);
    return () => clearInterval(interval);
  }, [isOpen, questionState?.id, questionState?.timer, questionState?.status]);

  if (!isOpen || !questionState) return null;

  const { question, status, is_correct, sequence_number } = questionState;
  const isPending = status === "PENDING_QUESTION";
  const isAnswered =
    status === "ANSWER_CORRECT" ||
    status === "ANSWER_INCORRECT" ||
    status === "PENDING_REWARD" ||
    status === "REWARD_CLAIMED";
  const isExpired =
    status === "EXPIRED" || (isPending && secondsRemaining <= 0);

  const getDifficultyBadge = (diff: string) => {
    switch (diff) {
      case "EASY":
        return <span className="badge badge-emerald">DỄ (EASY)</span>;
      case "HARD":
        return <span className="badge badge-rose">KHÓ (HARD)</span>;
      default:
        return <span className="badge badge-amber">TRUNG BÌNH (MEDIUM)</span>;
    }
  };

  const submitAnswer = async (answer: string) => {
    if (!isPending || isExpired || isSubmitting || matchEnded) return;

    if (!answer) {
      setErrorMsg("Vui lòng chọn hoặc nhập câu trả lời.");
      return;
    }

    try {
      setErrorMsg(null);
      const updated = await onSubmitAnswer(answer);
      if (updated.status === "PENDING_REWARD" && updated.reward_options) {
        onRewardTrigger(updated.reward_options, updated.id);
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Lỗi gửi câu trả lời.");
    }
  };

  const timerPercent = Math.min(
    100,
    Math.max(0, (secondsRemaining / (question.time_limit_seconds || 60)) * 100),
  );

  const timerColor =
    secondsRemaining <= 10
      ? "var(--accent-rose)"
      : secondsRemaining <= 25
        ? "var(--accent-amber)"
        : "var(--accent-cyan)";

  return (
    <div
      ref={dialog}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-label="Câu hỏi tri thức"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        backgroundColor: "rgba(0, 0, 0, 0.75)",
        backdropFilter: "blur(8px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "16px",
        animation: "fadeIn 0.2s ease-out",
      }}
    >
      <div
        className="glass-panel"
        style={{
          width: "100%",
          maxWidth: "680px",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          borderRadius: "16px",
          border: "1px solid rgba(255, 255, 255, 0.15)",
          boxShadow:
            "0 20px 50px rgba(0, 0, 0, 0.7), 0 0 30px rgba(56, 189, 248, 0.1)",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "18px 24px",
            borderBottom: "1px solid var(--border-subtle)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: "rgba(255, 255, 255, 0.02)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "8px",
                background: "rgba(56, 189, 248, 0.15)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--accent-cyan)",
              }}
            >
              <HelpCircle size={22} />
            </div>
            <div>
              <div
                style={{ display: "flex", alignItems: "center", gap: "8px" }}
              >
                <span style={{ fontWeight: 800, fontSize: "0.95rem" }}>
                  THỬ THÁCH CHIẾN LƯỢC #{sequence_number}{totalQuestions ? ` / ${totalQuestions}` : ''}
                </span>
                {getDifficultyBadge(question.difficulty)}
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-dim)" }}>
                Chủ đề: {question.category} • Loại: {question.type}
              </div>
            </div>
          </div>

          <button
            aria-label="Đóng câu hỏi"
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "var(--text-dim)",
              cursor: "pointer",
              padding: "6px",
              borderRadius: "6px",
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Live Timer Bar */}
        {isPending && !isExpired && !matchEnded && (
          <div
            style={{ background: "rgba(0, 0, 0, 0.4)", padding: "8px 24px" }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: "0.85rem",
                marginBottom: "6px",
              }}
            >
              <span
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  color: timerColor,
                  fontWeight: 600,
                }}
              >
                <Clock size={16} /> Thời gian còn lại:
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontWeight: 800,
                  fontSize: "1rem",
                  color: timerColor,
                }}
              >
                {secondsRemaining}s
              </span>
            </div>
            <div
              style={{
                height: "6px",
                background: "rgba(255, 255, 255, 0.1)",
                borderRadius: "3px",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${timerPercent}%`,
                  height: "100%",
                  background: timerColor,
                  transition: "width 0.5s linear, background 0.3s ease",
                  boxShadow: `0 0 8px ${timerColor}`,
                }}
              />
            </div>
          </div>
        )}

        {/* Modal Body */}
        <div style={{ padding: "24px", overflowY: "auto", flex: 1 }}>
          {matchEnded && <p role="status">Trận đấu đã kết thúc. Câu trả lời và phần thưởng không còn khả dụng. Đóng cửa sổ để xem kết quả.</p>}
          {status === "REWARD_CLAIMED" && <p role="status">Phần thưởng này đã được đồng đội nhận thành công.</p>}
          {/* Question Content */}
          <div
            style={{
              fontSize: "15px",
              fontWeight: 600,
              lineHeight: 1.6,
              color: "#ffffff",
              marginBottom: "20px",
              padding: "16px",
              background: "rgba(255, 255, 255, 0.03)",
              borderRadius: "10px",
              border: "1px solid rgba(255, 255, 255, 0.06)",
            }}
          >
            {question.content}
          </div>

          {/* Error Message if any */}
          {errorMsg && (
            <div
              style={{
                marginBottom: "16px",
                padding: "10px 14px",
                borderRadius: "8px",
                background: "rgba(244, 63, 94, 0.15)",
                border: "1px solid rgba(244, 63, 94, 0.4)",
                color: "var(--accent-rose)",
                fontSize: "0.85rem",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <AlertTriangle size={16} /> {errorMsg}
            </div>
          )}

          {/* Interactive State: Answering */}
          {isPending && !isExpired && !matchEnded && (
            <form onSubmit={(e) => {
              e.preventDefault();
              if (question.type !== "MULTIPLE_CHOICE") {
                void submitAnswer(textAnswer.trim());
              }
            }}>
              {question.type === "MULTIPLE_CHOICE" && question.options ? (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "10px",
                  }}
                >
                  {question.options.map((opt, idx) => {
                    const optKey =
                      typeof opt === "object"
                        ? opt.key
                        : String.fromCharCode(65 + idx);
                    const optText = typeof opt === "object" ? opt.text : opt;
                    const isSelected = selectedOption === optKey;

                    return (
                      <button
                        type="button"
                        key={optKey}
                        aria-label={`${optKey}. ${optText}`}
                        onClick={() => {
                          setSelectedOption(optKey);
                          void submitAnswer(optKey);
                        }}
                        disabled={isSubmitting}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "14px",
                          padding: "14px 18px",
                          borderRadius: "10px",
                          border: isSelected
                            ? "2px solid var(--accent-cyan)"
                            : "1px solid rgba(255, 255, 255, 0.1)",
                          background: isSelected
                            ? "rgba(56, 189, 248, 0.12)"
                            : "rgba(0, 0, 0, 0.3)",
                          cursor: isSubmitting ? "not-allowed" : "pointer",
                          textAlign: "left",
                          transition: "all 0.15s ease",
                          color: "#ffffff",
                        }}
                      >
                        <div
                          style={{
                            width: "32px",
                            height: "32px",
                            borderRadius: "50%",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontWeight: 800,
                            fontFamily: "var(--font-mono)",
                            fontSize: "0.9rem",
                            background: isSelected
                              ? "var(--accent-cyan)"
                              : "rgba(255, 255, 255, 0.1)",
                            color: isSelected ? "#000000" : "var(--text-main)",
                            flexShrink: 0,
                          }}
                        >
                          {optKey}
                        </div>
                        <div
                          style={{
                            fontSize: "14px",
                            fontWeight: 400,
                            flex: 1,
                          }}
                        >
                          {optText}
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div>
                  <label
                    style={{
                      display: "block",
                      fontSize: "0.85rem",
                      fontWeight: 600,
                      color: "var(--text-dim)",
                      marginBottom: "8px",
                    }}
                  >
                    NHẬP ĐÁP ÁN CỦA ĐỘI:
                  </label>
                  <input
                    type="text"
                    value={textAnswer}
                    onChange={(e) => setTextAnswer(e.target.value)}
                    placeholder="Nhập câu trả lời hoặc kết quả giải mã..."
                    disabled={isSubmitting}
                    autoFocus
                    style={{
                      width: "100%",
                      padding: "12px 16px",
                      borderRadius: "8px",
                      background: "rgba(0, 0, 0, 0.4)",
                      border: "1px solid var(--border-subtle)",
                      color: "#ffffff",
                      fontFamily: "var(--font-mono)",
                      fontSize: "1rem",
                      outline: "none",
                    }}
                  />
                </div>
              )}

              {/* Submit Action */}
              <div
                style={{
                  marginTop: "24px",
                  display: "flex",
                  justifyContent: "flex-end",
                  gap: "12px",
                }}
              >
                {question.type === "MULTIPLE_CHOICE" && (
                  <span role="status" style={{
                    display: "flex", alignItems: "center", gap: "8px",
                    marginRight: "auto", color: "var(--text-dim)", fontSize: "0.85rem",
                  }}>
                    {isSubmitting ? (
                      <><Loader2 size={18} className="animate-spin" /> Đang kiểm tra...</>
                    ) : "Chọn đáp án để xem kết quả ngay."}
                  </span>
                )}
                <button
                  type="button"
                  aria-label="Đóng câu hỏi"
                  onClick={onClose}
                  disabled={isSubmitting}
                  className="btn-secondary"
                  style={{ padding: "10px 18px", fontSize: "0.9rem" }}
                >
                  Tạm ẩn
                </button>
                {question.type !== "MULTIPLE_CHOICE" && (
                <button
                  type="submit"
                  disabled={
                    isSubmitting || !textAnswer.trim()
                  }
                  className="btn-primary"
                  style={{
                    padding: "10px 24px",
                    fontSize: "0.95rem",
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                  }}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 size={18} className="animate-spin" /> Đang kiểm
                      tra...
                    </>
                  ) : (
                    <>
                      <Send size={18} /> Xác Nhận Nộp Bài
                    </>
                  )}
                </button>
                )}
              </div>
            </form>
          )}

          {/* Feedback: Answer Submitted / Resolved */}
          {isAnswered && (
            <div
              style={{ display: "flex", flexDirection: "column", gap: "16px" }}
            >
              <div
                style={{
                  padding: "20px",
                  borderRadius: "12px",
                  background: is_correct
                    ? "rgba(16, 185, 129, 0.12)"
                    : "rgba(244, 63, 94, 0.12)",
                  border: is_correct
                    ? "1px solid rgba(16, 185, 129, 0.4)"
                    : "1px solid rgba(244, 63, 94, 0.4)",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "16px",
                }}
              >
                {is_correct ? (
                  <CheckCircle2
                    size={32}
                    style={{ color: "var(--accent-emerald)", flexShrink: 0 }}
                  />
                ) : (
                  <XCircle
                    size={32}
                    style={{ color: "var(--accent-rose)", flexShrink: 0 }}
                  />
                )}
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      fontSize: "1.2rem",
                      fontWeight: 800,
                      color: is_correct
                        ? "var(--accent-emerald)"
                        : "var(--accent-rose)",
                      marginBottom: "6px",
                    }}
                  >
                    {is_correct
                      ? "CHÍNH XÁC! ĐÃ MỞ KHÓA PHẦN THƯỞNG"
                      : "ĐÁP ÁN CHƯA CHÍNH XÁC"}
                  </div>
                  <div
                    style={{
                      fontSize: "0.9rem",
                      color: "var(--text-main)",
                      lineHeight: 1.5,
                    }}
                  >
                    {is_correct
                      ? questionState.reward_options?.coin_distribution?.length
                        ? "Đội của bạn đã trả lời đúng! Hãy chọn Túi coin bí ẩn hoặc Mở khóa một Đơn vị/Công sự mới."
                        : `Đội của bạn đã trả lời đúng! Hãy chọn nhận ${questionState.reward_options?.coin_amount ?? 30} Coin hoặc Mở khóa một Đơn vị/Công sự mới.`
                      : "Đội của bạn không nhận được phần thưởng cho câu hỏi này. Trận đấu vẫn tiếp tục."}
                  </div>
                  {question.explanation && (
                    <div
                      style={{
                        marginTop: "12px",
                        padding: "10px 14px",
                        background: "rgba(0, 0, 0, 0.25)",
                        borderRadius: "8px",
                        fontSize: "0.85rem",
                        color: "var(--text-muted)",
                      }}
                    >
                      <strong style={{ color: "var(--accent-cyan)" }}>
                        Giải thích:{" "}
                      </strong>
                      {question.explanation}
                    </div>
                  )}
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-end",
                  flexWrap: "wrap",
                  gap: "12px",
                  marginTop: "12px",
                }}
              >
                {status === "PENDING_REWARD" && questionState.reward_options ? (
                  <button
                    onClick={() =>
                      onRewardTrigger(
                        questionState.reward_options!,
                        questionState.id,
                      )
                    }
                    className="btn-primary"
                    style={{
                      padding: "12px 28px",
                      fontSize: "1rem",
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      background:
                        "linear-gradient(135deg, #10b981 0%, #059669 100%)",
                    }}
                  >
                    Tiến Hành Chọn Phần Thưởng <ArrowRight size={18} />
                  </button>
                ) : (
                  <button
                    aria-label="Đóng câu hỏi"
                    onClick={onClose}
                    className="btn-secondary"
                    style={{ padding: "10px 20px", fontSize: "0.9rem" }}
                  >
                    Đóng và Tiếp tục trận đấu
                  </button>
                )}
                {status === "ANSWER_INCORRECT" && onNextQuestion && !matchEnded &&
                  (totalQuestions === undefined || sequence_number < totalQuestions) && (
                  <button
                    type="button"
                    onClick={async () => {
                      if (isLoadingNext) return;
                      setIsLoadingNext(true);
                      try {
                        await onNextQuestion();
                      } finally {
                        setIsLoadingNext(false);
                      }
                    }}
                    disabled={isLoadingNext}
                    className="btn-primary"
                    style={{ padding: "10px 20px", fontSize: "0.9rem", display: "flex", alignItems: "center", gap: "8px" }}
                  >
                    {isLoadingNext ? <><Loader2 size={18} className="animate-spin" /> Đang tải câu hỏi...</> : <>Câu hỏi tiếp theo <ArrowRight size={18} /></>}
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Feedback: Expired */}
          {isExpired && !isAnswered && (
            <div
              style={{
                padding: "24px",
                borderRadius: "12px",
                background: "rgba(244, 63, 94, 0.1)",
                border: "1px solid rgba(244, 63, 94, 0.3)",
                textAlign: "center",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "12px",
              }}
            >
              <Clock size={40} style={{ color: "var(--accent-rose)" }} />
              <div
                style={{
                  fontSize: "1.2rem",
                  fontWeight: 800,
                  color: "var(--accent-rose)",
                }}
              >
                {is_correct ? "ĐÃ HẾT HẠN CHỌN PHẦN THƯỞNG" : "ĐÃ HẾT THỜI GIAN TRẢ LỜI"}
              </div>
              <div
                style={{
                  fontSize: "0.9rem",
                  color: "var(--text-dim)",
                  maxWidth: "420px",
                }}
              >
                {is_correct
                  ? "Thời gian chọn phần thưởng đã kết thúc theo quy tắc của trận đấu. Chưa có xu hoặc công nghệ nào được nhận."
                  : "Câu hỏi đã hết hạn thời gian. Không nhận được phần thưởng cho thử thách này."}
              </div>
              <button
                aria-label="Đóng câu hỏi"
                onClick={onClose}
                className="btn-secondary"
                style={{ marginTop: "12px", padding: "8px 20px" }}
              >
                Tiếp tục trận đấu
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
