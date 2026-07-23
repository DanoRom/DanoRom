"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, clearToken, getToken } from "@/lib/api";

export default function NavAuth() {
  const [username, setUsername] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      setLoaded(true);
      return;
    }
    api
      .me()
      .then((res) => setUsername(res.username))
      .catch(() => setUsername(null))
      .finally(() => setLoaded(true));
  }, []);

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      /* session may already be gone server-side; clear locally regardless */
    } finally {
      clearToken();
      setUsername(null);
    }
  };

  if (!loaded) return null;

  if (!username) {
    return <Link href="/login">Log in</Link>;
  }

  return (
    <span>
      @{username} ·{" "}
      <button type="button" className="link-btn" onClick={logout}>
        Log out
      </button>
    </span>
  );
}
