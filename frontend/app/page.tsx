"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, Project } from "@/lib/api";

const TEMPLATES = [
  { value: "blank", label: "Blank project" },
  { value: "nextjs-app", label: "Next.js app" },
  { value: "fastapi-api", label: "FastAPI service" },
  { value: "fullstack", label: "Full-stack (Next.js + FastAPI)" },
];

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadError, setLoadError] = useState("");

  const refresh = useCallback(() => {
    api
      .listProjects()
      .then((list) => {
        setProjects(list);
        setLoadError("");
      })
      .catch(() =>
        setLoadError("Backend unreachable — start it with: uvicorn app.main:app --reload")
      );
  }, []);

  useEffect(refresh, [refresh]);

  return (
    <main className="page">
      <h1>Dashboard</h1>
      <p className="subtitle">
        Start a new project or add an existing one — the engine evaluates its build
        stage and maps the branched pathway to completion.
      </p>

      <div className="grid-2">
        <StartProjectCard onCreated={refresh} />
        <AddProjectCard onCreated={refresh} />
      </div>

      <h2 style={{ marginBottom: "1rem" }}>Your projects</h2>
      {loadError && <p className="error">{loadError}</p>}
      {!loadError && projects.length === 0 && (
        <p className="muted">No projects yet — create or upload one above.</p>
      )}
      {projects.map((p) => (
        <Link key={p.id} href={`/projects/${p.id}`}>
          <div className="project-row">
            <div>
              <strong>{p.name}</strong>
              <div className="muted" style={{ fontSize: "0.85rem" }}>
                {p.source_type === "upload" ? "Uploaded repo" : `Template: ${p.template}`}
              </div>
            </div>
            <span className={`badge ${p.stage === "unevaluated" ? "" : "red"}`}>
              {p.stage}
            </span>
          </div>
        </Link>
      ))}
    </main>
  );
}

function StartProjectCard({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [template, setTemplate] = useState("blank");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!name.trim()) {
      setError("Give the project a name.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.createProject({ name, description, template });
      setName("");
      setDescription("");
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create project");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h2>Start Project</h2>
      <p>Spin up a new project from a template.</p>
      <label>Name</label>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="my-app" />
      <label>Description</label>
      <input
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="What are you building?"
      />
      <label>Template</label>
      <select value={template} onChange={(e) => setTemplate(e.target.value)}>
        {TEMPLATES.map((t) => (
          <option key={t.value} value={t.value}>
            {t.label}
          </option>
        ))}
      </select>
      <button className="cta" onClick={submit} disabled={busy}>
        {busy ? "Creating…" : "Start Project"}
      </button>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function AddProjectCard({ onCreated }: { onCreated: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [githubUrl, setGithubUrl] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submitImport = async () => {
    if (!githubUrl.trim()) {
      setError("Paste a GitHub repository URL.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.importProject(githubUrl, name);
      setGithubUrl("");
      setName("");
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  };

  const submitUpload = async () => {
    if (!file) {
      setError("Choose a .zip archive of your project.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.uploadProject(file, name);
      setFile(null);
      setName("");
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card blue">
      <h2>Add Project</h2>
      <p>Import a GitHub repo by URL, or upload an existing file tree as a .zip archive.</p>
      <label>Project name (optional)</label>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="existing-app" />

      <label>GitHub URL</label>
      <input
        value={githubUrl}
        onChange={(e) => setGithubUrl(e.target.value)}
        placeholder="https://github.com/owner/repo"
      />
      <button
        className="cta"
        onClick={submitImport}
        disabled={busy}
        style={{ marginBottom: "1.25rem" }}
      >
        {busy ? "Importing…" : "Import from GitHub"}
      </button>

      <label>Archive</label>
      <input
        type="file"
        accept=".zip"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <button className="cta" onClick={submitUpload} disabled={busy}>
        {busy ? "Uploading…" : "Add Project"}
      </button>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
