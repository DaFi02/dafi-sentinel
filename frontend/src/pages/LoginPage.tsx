import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useSession } from "../auth/useAuth";
import { ApiError } from "../api/client";

type LocationState = { from?: { pathname?: string } };

export function LoginPage() {
  const { session, login, hydrated } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  // R2 med: the prior form pre-filled the seeded analyst credentials
  // (``ada`` / ``hunter2!``) so anyone opening the dev server could
  // sign in with a single click. The dev seed is documented in the
  // README (use ``DAFI_DEV_PASSWORD`` to pin a stable credential),
  // but the form no longer surfaces the plaintext. The user MUST
  // type the username and password themselves.
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (!hydrated) {
    return <p className="muted">loading…</p>;
  }
  if (session) {
    const state = (location.state ?? null) as LocationState | null;
    const target = state?.from?.pathname ?? "/evidence";
    return <Navigate to={target} replace />;
  }

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(username, password);
      const state = (location.state ?? null) as LocationState | null;
      const target = state?.from?.pathname ?? "/evidence";
      navigate(target, { replace: true });
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.detail);
      } else if (caught instanceof Error) {
        setError(caught.message);
      } else {
        setError("login failed");
      }
    } finally {
      setPending(false);
    }
  };

  return (
    <main>
      <h2>Sign in</h2>
      <p className="muted">Enter the credentials supplied by your operator. The dev server logs the seeded password on boot (see the README).</p>
      <form onSubmit={(event) => void onSubmit(event)}>
        <label htmlFor="username">username</label>
        <input
          id="username"
          className="input"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
        />
        <label htmlFor="password">password</label>
        <input
          id="password"
          type="password"
          className="input"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
        />
        <button className="button" type="submit" disabled={pending || !username || !password}>
          {pending ? "signing in…" : "sign in"}
        </button>
      </form>
      {error ? <p className="error">{error}</p> : null}
    </main>
  );
}
