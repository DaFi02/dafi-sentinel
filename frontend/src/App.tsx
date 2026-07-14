// Minimal app shell — the routes and pages land in the next work unit.
// This file stays small so the SessionProvider/BrowserRouter/QueryClient
// tree can be reviewed alongside the auth tests in isolation.

import { Route, Routes } from "react-router-dom";

import { AuthGate } from "./auth/AuthGate";
import { LoginPage } from "./pages/LoginPage";

export default function App() {
  return (
    <div className="app">
      <header className="app__header">
        <h1>DAFI Sentinel</h1>
      </header>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/protected"
          element={
            <AuthGate>
              <main>
                <h2>protected</h2>
                <p>You are signed in.</p>
              </main>
            </AuthGate>
          }
        />
      </Routes>
    </div>
  );
}
