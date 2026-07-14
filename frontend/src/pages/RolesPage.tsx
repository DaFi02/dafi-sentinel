import { useState } from "react";

import { useRoles } from "../api/queries";
import { useMeProbe } from "../auth/useAuth";
import { ApiError } from "../api/client";

export function RolesPage() {
  const me = useMeProbe(true);
  const [userId, setUserId] = useState<string | null>(null);
  // Probe sets the default userId once the session hydrates.
  if (me.data && userId === null) {
    setUserId(me.data.user_id);
  }
  const roles = useRoles(userId, true);

  if (!me.data) {
    return <p className="muted">loading…</p>;
  }
  if (roles.isLoading) {
    return <p className="muted">loading roles…</p>;
  }
  if (roles.error instanceof ApiError) {
    if (roles.error.status === 403) {
      return <p className="error">403 — you can only inspect your own role set.</p>;
    }
    if (roles.error.status === 404) {
      return <p className="error">404 — user not found.</p>;
    }
    return <p className="error">{roles.error.status} — {roles.error.detail}</p>;
  }
  if (roles.error) {
    return <p className="error">{roles.error.message}</p>;
  }
  if (!roles.data) {
    return <p className="muted">no role data</p>;
  }
  return (
    <main>
      <h2>Roles for {roles.data.display_name}</h2>
      <p className="muted">user id: <code>{roles.data.user_id}</code></p>
      <section className="card">
        <h3>roles</h3>
        {roles.data.roles.length === 0 ? <p className="muted">no roles</p> : (
          <ul>
            {roles.data.roles.map((role) => (
              <li key={role}><code>{role}</code></li>
            ))}
          </ul>
        )}
        <h3>permissions</h3>
        {roles.data.permissions.length === 0 ? <p className="muted">no permissions</p> : (
          <ul>
            {roles.data.permissions.map((permission) => (
              <li key={permission}><code>{permission}</code></li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
