import { useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import { QuestionBankPreview, StagedQuestionBank } from '../types/questionBank';

export function QuestionBankUpload({ onChange, disabled = false }: {
  onChange: (bank: StagedQuestionBank | null, ready: boolean) => void;
  disabled?: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<QuestionBankPreview | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [confirmed, setConfirmed] = useState(false);
  const token = useRef(crypto.randomUUID());
  const version = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const selectedInput = useRef<HTMLInputElement>(null);
  useEffect(() => () => { version.current++; controller.current?.abort(); }, []);

  const choose = (next: File | null) => {
    version.current++; controller.current?.abort();
    setBusy(false); setPreview(null); setError(''); setConfirmed(false); setProgress(0);
    if (preview) void api.deleteQuestionBank(preview.id, token.current).catch(() => {});
    token.current = crypto.randomUUID(); setFile(next); onChange(null, !next);
    if (!next && selectedInput.current) selectedInput.current.value = '';
    if (next && !next.name.toLowerCase().endsWith('.xlsx')) setError('Chỉ hỗ trợ tệp .xlsx.');
  };
  const validate = async () => {
    if (!file || busy) return;
    const requestVersion = ++version.current;
    controller.current?.abort(); controller.current = new AbortController();
    setBusy(true); setError(''); setConfirmed(false); onChange(null, false);
    try {
      const result = await api.uploadQuestionBank(file, token.current, setProgress, controller.current.signal);
      if (requestVersion === version.current) setPreview(result);
    } catch (e) {
      if (requestVersion === version.current) setError(e instanceof Error ? e.message : 'Không thể kiểm tra tệp.');
    } finally { if (requestVersion === version.current) setBusy(false); }
  };
  const page = async (number: number) => {
    if (!preview || busy) return;
    const requestVersion = version.current;
    setBusy(true); setError('');
    try { const result = await api.previewQuestionBank(preview.id, token.current, number); if (requestVersion === version.current) setPreview(result); }
    catch (e) { if (requestVersion === version.current) setError(e instanceof Error ? e.message : 'Không thể xem trước.'); }
    finally { if (requestVersion === version.current) setBusy(false); }
  };
  return <fieldset disabled={disabled} className="question-upload" style={{ border: '1px solid var(--border-subtle)', borderRadius: 12, padding: 16, marginBottom: 18, minWidth: 0 }}>
    <legend>Ngân hàng câu hỏi Excel</legend>
    <p style={{ fontSize: '.82rem', color: 'var(--text-muted)' }}>Tải .xlsx theo mẫu STT · Câu hỏi · A–D · Đáp án. Có thể bỏ qua để dùng bộ câu hỏi mặc định.</p>
    <input ref={selectedInput} aria-label="Tệp ngân hàng câu hỏi" type="file" accept=".xlsx" onChange={e => choose(e.target.files?.[0] || null)} style={{ width: '100%', margin: '10px 0' }} />
    {file && <>
      <p style={{ overflowWrap: 'anywhere' }}>{file.name}</p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" className="btn-secondary" onClick={() => void validate()} disabled={busy || !file.name.toLowerCase().endsWith('.xlsx')}>Kiểm tra & xem trước</button>
        <button type="button" className="btn-secondary" onClick={() => choose(null)}>Gỡ tệp</button>
      </div>
    </>}
    {busy && <div role="status"><progress aria-label="Tiến độ tải lên" value={progress} max={100} /> {progress < 100 ? `Đang tải ${progress}%` : 'Đang kiểm tra / tải xem trước…'}</div>}
    {error && <p role="alert" style={{ color: 'var(--accent-rose)' }}>{error}</p>}
    {preview && <div aria-live="polite" style={{ marginTop: 12 }}>
      <strong>{preview.valid_questions} câu hợp lệ · {preview.invalid_questions} câu lỗi</strong>
      {preview.errors.length > 0 && <div role="alert" style={{ maxHeight: 160, overflowY: 'auto', color: 'var(--accent-rose)' }}>
        {preview.errors.map((e, i) => <p key={i}>{e.sheet} · dòng {e.row} · {e.field}: {e.message}</p>)}
      </div>}
      <div style={{ maxHeight: 220, overflowY: 'auto', margin: '12px 0' }}>
        {preview.questions.map(q => <article key={q.id} style={{ padding: '12px 0', borderBottom: '1px solid var(--border-subtle)' }}>
          <strong>{q.import_order}. {q.content}</strong>
          {q.options.map(o => <p key={o.key} style={{ fontSize: '.85rem', marginTop: 4 }}>{o.key}. {o.text}{q.answer_key === o.key ? ' ✓' : ''}</p>)}
          <small>Đáp án: {q.answer_key} · {q.import_metadata.sheet}, dòng {q.import_metadata.row}</small>
        </article>)}
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <button type="button" className="btn-secondary" disabled={busy || preview.page <= 1} onClick={() => void page(preview.page - 1)}>Trước</button>
        <small>Trang {preview.page}/{Math.max(1, Math.ceil(preview.valid_questions / preview.page_size))}</small>
        <button type="button" className="btn-secondary" disabled={busy || preview.page * preview.page_size >= preview.valid_questions} onClick={() => void page(preview.page + 1)}>Sau</button>
      </div>
      {preview.can_create && <label style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <input type="checkbox" checked={confirmed} onChange={e => { setConfirmed(e.target.checked); onChange({ id: preview.id, token: token.current }, e.target.checked); }} />
        Tôi đã xem trước và chọn bộ câu hỏi này
      </label>}
      {!preview.can_create && <p>Hãy sửa lỗi và tải lại tệp trước khi tạo phòng.</p>}
    </div>}
  </fieldset>;
}
