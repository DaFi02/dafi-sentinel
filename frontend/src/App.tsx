import { NavLink, Route, Routes } from "react-router-dom";

import { AuthGate } from "./auth/AuthGate";
import { useSession } from "./auth/useAuth";
import { LoginPage } from "./pages/LoginPage";
import { EvidenceListPage } from "./pages/EvidenceListPage";
import { EvidenceDetailPage } from "./pages/EvidenceDetailPage";
import { QAPage } from "./pages/QAPage";
import { ChartsPage } from "./pages/ChartsPage";
import { RolesPage } from "./pages/RolesPage";
import { AuditsPage } from "./pages/AuditsPage";

export default function App() {
  const { session, logout } = useSession();

  return (
    <div className="app">
      <header className="app__header">
        <h1>DAFI Sentinel</h1>
        {session ? (
          <div>
            <span className="muted">{session.display_name}</span>
            {" · "}
            <button type="button" className="button secondary" onClick={() => void logout()}>
              logout
            </button>
          </div>
        ) : (
          <NavLink to="/login" className="button">
            sign in
          </NavLink>
        )}
      </header>

      {session ? (
        <nav className="app__nav" aria-label="primary">
          <NavLink to="/evidence" className={({ isActive }) => (isActive ? "active" : "")}>
            evidence
          </NavLink>
          <NavLink to="/qa" className={({ isActive }) => (isActive ? "active" : "")}>
            q&amp;a
          </NavLink>
          <NavLink to="/charts" className={({ isActive }) => (isActive ? "active" : "")}>
            charts
          </NavLink>
          <NavLink to="/roles" className={({ isActive }) => (isActive ? "active" : "")}>
            roles
          </NavLink>
          <NavLink to="/audits" className={({ isActive }) => (isActive ? "active" : "")}>
            audits
          </NavLink>
        </nav>
      ) : null}

      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/evidence"
          element={
            <AuthGate>
              <EvidenceListPage />
            </AuthGate>
          }
        />
        <Route
          path="/evidence/:evidenceId"
          element={
            <AuthGate>
              <EvidenceDetailPage />
            </AuthGate>
          }
        />
        <Route
          path="/qa"
          element={
            <AuthGate>
              <QAPage />
            </AuthGate>
          }
        />
        <Route
          path="/charts"
          element={
            <AuthGate>
              <ChartsPage />
            </AuthGate>
          }
        />
        <Route
          path="/roles"
          element={
            <AuthGate>
              <RolesPage />
            </AuthGate>
          }
        />
        <Route
          path="/audits"
          element={
            <AuthGate>
              <AuditsPage />
            </AuthGate>
          }
        />
        <Route path="*" element={<RedirectToEvidence />} />
      </Routes>
    </div>
  );
}

function RedirectToEvidence() {
  return (
    <main>
      <p className="muted">Pick a page from the navigation.</p>
    </main>
  );
}
