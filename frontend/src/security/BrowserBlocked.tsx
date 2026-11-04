import './browserBlocked.css';

export function BrowserBlocked() {
  return (
    <main className="browser-blocked" role="alert">
      <section className="browser-blocked-card">
        <span className="browser-blocked-icon" aria-hidden="true">🔒</span>
        <h1>⚠️ Hành vi gian lận bị phát hiện! Trò chơi đã bị khóa.</h1>
        <p>Phiên chơi đã bị khóa do phát hiện thao tác mở công cụ kiểm tra trình duyệt.</p>
        <p>Hãy đóng DevTools, tải lại trang và vào lại phòng để tiếp tục.</p>
        <button type="button" onClick={() => window.location.reload()}>Tải lại trang</button>
      </section>
    </main>
  );
}
