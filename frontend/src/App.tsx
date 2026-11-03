import React, { lazy, Suspense } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Link,
  useLocation,
} from "react-router-dom";
import { Shield } from "lucide-react";
import { LandingPage } from "./pages/LandingPage";
import { JoinMatchPage } from "./pages/JoinMatchPage";
import { LobbyPage } from "./pages/LobbyPage";
const BattlePage = lazy(() =>
  import("./pages/BattlePage").then((module) => ({
    default: module.BattlePage,
  })),
);
import { HostDashboardPage } from "./pages/HostDashboardPage";
import { ResultsPage } from "./pages/ResultsPage";

const AppContent: React.FC = () => {
  const pathname = useLocation().pathname;
  const isBattle = pathname.startsWith("/battle");
  const isHome = pathname === "/";
  const usesWoodlandStyle = isHome || pathname === "/join" || pathname.startsWith("/lobby") || pathname === "/host" || pathname.startsWith("/results");
  return (
    <div className="app-container">
      {/* Navigation Header */}
      {!isBattle && (
        <header className={`navbar${usesWoodlandStyle ? " navbar-home" : ""}`}>
          <Link to="/" style={{ textDecoration: "none" }} className="nav-brand">
            <Shield size={24} style={{ color: "var(--accent-cyan)" }} />
            <span>THỦ THÀNH CHIẾN THUẬT</span>
          </Link>

          <nav className="nav-links">
            <Link to="/" className="nav-link">
              Trang chủ
            </Link>
            <Link to="/join" className="nav-link">
              Vào phòng đấu
            </Link>
            <Link to="/lobby" className="nav-link">
              Phòng chờ
            </Link>
            <Link to="/battle" className="nav-link">
              Bản đồ chiến trường
            </Link>
            <Link to="/host" className="nav-link">
              Điều khiển Host
            </Link>
          </nav>
        </header>
      )}

      {/* Routes */}
      <main style={{ flex: 1 }}>
        <Suspense
          fallback={
            <div className="game-loading-screen">Đang mở chiến trường…</div>
          }
        >
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/join" element={<JoinMatchPage />} />
            <Route path="/lobby" element={<LobbyPage />} />
            <Route path="/lobby/:matchId" element={<LobbyPage />} />
            <Route path="/battle" element={<BattlePage />} />
            <Route path="/battle/:matchId" element={<BattlePage />} />
            <Route path="/host" element={<HostDashboardPage />} />
            <Route path="/results" element={<ResultsPage />} />
            <Route path="/results/:matchId" element={<ResultsPage />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
};

export const App: React.FC = () => (
  <BrowserRouter>
    <AppContent />
  </BrowserRouter>
);

export default App;
