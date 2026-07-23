"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!username.trim() || !password) {
      setError("Enter a username and password.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result =
        mode === "login"
          ? await api.login(username.trim(), password)
          : await api.register(username.trim(), password);
      setToken(result.token);
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const switchMode = () => {
    setMode((m) => (m === "login" ? "register" : "login"));
    setError("");
  };

  return (
    <main className="page" style={{ maxWidth: "420px" }}>
      <div className="card">
        <h2>{mode === "login" ? "Log in" : "Create an account"}</h2>
        <p>
          {mode === "login"
            ? "Sign in to keep your own projects private."
            : "Accounts are optional — the platform stays fully usable without one."}
        </p>
        <label>Username</label>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="3-30 chars: letters, numbers, - or _"
          autoComplete="username"
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <label>Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 8 characters"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <button className="cta full" onClick={submit} disabled={busy}>
          {busy ? "Working…" : mode === "login" ? "Log in" : "Register"}
        </button>
        {error && <p className="error">{error}</p>}
        <p className="muted" style={{ marginTop: "1rem", fontSize: "0.85rem" }}>
          {mode === "login" ? "Need an account? " : "Already have an account? "}
          <button type="button" className="link-btn" onClick={switchMode}>
            {mode === "login" ? "Register" : "Log in"}
          </button>
        </p>
      </div>
    </main>
  );
}
