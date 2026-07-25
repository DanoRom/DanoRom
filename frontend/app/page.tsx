"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, Project, Stats, VersionInfo } from "@/lib/api";
import StatsRow from "@/components/StatsRow";

const TEMPLATES = [
  { value: "blank", label: "Blank project" },
  { value: "nextjs-app", label: "Next.js app" },
  { value: "fastapi-api", label: "FastAPI service" },
  { value: "fullstack", label: "Full-stack (Next.js + FastAPI)" },
];

const STAGE_FILTERS = [
  "all",
  "unevaluated",
  "ideation",
  "scaffolding",
  "feature-development",
  "testing",
  "deployment",
  "maintenance",
];

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [version, setVersion] = useState<VersionInfo | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [stageFilter, setStageFilter] = useState("all");

  const load = useCallback((q: string, stage: string) => {
    setLoading(true);
    api
      .listProjects({ q: q || undefined, stage: stage === "all" ? undefined : stage })
      .then((list) => {
        setProjects(list);
        setLoadError("");
      })
      .catch(() =>
        setLoadError("Backend unreachable — start it with `python dev.py` in the backend folder.")
      )
      .finally(() => setLoading(false));
  }, []);

  const refreshStats = useCallback(() => {
    api.getStats().then(setStats).catch(() => setStats(null));
  }, []);

  // Debounce search + filter changes into a single request.
  useEffect(() => {
    const t = setTimeout(() => load(query, stageFilter), 250);
    return () => clearTimeout(t);
  }, [query, stageFilter, load]);

  useEffect(() => {
    refreshStats();
    api.getVersion().then(setVersion).catch(() => setVersion(null));
  }, [refreshStats]);

  const onCreated = useCallback(() => {
    load(query, stageFilter);
    refreshStats();
  }, [load, query, stageFilter, refreshStats]);

  const filtering = query.trim() !== "" || stageFilter !== "all";

  return (
    <main className="page">
      <h1>Dashboard</h1>
      <p className="subtitle">
        Start a new project or add an existing one — the engine evaluates its build
        stage and maps the branched pathway to completion.
      </p>

      {stats && stats.total_projects > 0 && <StatsRow stats={stats} />}

      <div className="grid-2">
        <StartProjectCard onCreated={onCreated} />
        <AddProjectCard onCreated={onCreated} />
      </div>

      <div className="projects-header">
        <h2>Your projects</h2>
        <div className="filters">
          <input
            className="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name…"
          />
          <select value={stageFilter} onChange={(e) => setStageFilter(e.target.value)}>
            {STAGE_FILTERS.map((s) => (
              <option key={s} value={s}>
                {s === "all" ? "All stages" : s}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loadError && <p className="error">{loadError}</p>}

      {loading && !loadError && (
        <div>
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton-row" />
          ))}
        </div>
      )}

      {!loading && !loadError && projects.length === 0 && (
        <p className="muted">
          {filtering
            ? "No projects match your search."
            : "No projects yet — create or upload one above."}
        </p>
      )}

      {!loading &&
        projects.map((p) => (
          <Link key={p.id} href={`/projects/${p.id}`}>
            <div className="project-row">
              <div>
                <strong>{p.name}</strong>
                <div className="muted" style={{ fontSize: "0.85rem" }}>
                  {p.source_type === "upload"
                    ? "Uploaded repo"
                    : p.source_type === "github"
                    ? "Imported from GitHub"
                    : `Template: ${p.template}`}
                </div>
              </div>
              <span className={`badge ${p.stage === "unevaluated" ? "" : "red"}`}>
                {p.stage}
              </span>
            </div>
          </Link>
        ))}

      {version && (
        <p className="muted" style={{ fontSize: "0.78rem", marginTop: "2rem" }}>
          v{version.version} · {version.engine === "gemini" ? "Gemini AI" : "heuristic"} engine
        </p>
      )}
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
  const [token, setToken] = useState("");
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
      await api.importProject(githubUrl, name, token);
      setGithubUrl("");
      setToken("");
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
      <label>GitHub token (only for private repos)</label>
      <input
        type="password"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        placeholder="ghp_… — leave blank for public repos"
        autoComplete="off"
      />
      <p className="muted" style={{ fontSize: "0.75rem", marginTop: "-0.4rem", marginBottom: "0.85rem" }}>
        Private repo? Create a free{" "}
        <a
          href="https://github.com/settings/tokens/new?scopes=repo&description=Developer%20Platform%20import"
          target="_blank"
          rel="noopener noreferrer"
          style={{ textDecoration: "underline" }}
        >
          read-only token
        </a>{" "}
        and paste it here. It's used once for this import and never saved.
      </p>
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
