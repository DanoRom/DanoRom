"use client";

import { useState } from "react";
import { api, ProjectTree } from "@/lib/api";

const TEST_MARKERS = ["test", "tests", "spec", "__tests__"];
const CI_NAMES = [".github", "workflows", ".gitlab-ci.yml", ".circleci", "jenkinsfile"];
const DOCKER_NAMES = ["dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"];

function lineKind(line: string): "test" | "ci" | "docker" | null {
  const name = line.trim().replace(/\/$/, "").toLowerCase();
  if (!name) return null;
  if (DOCKER_NAMES.includes(name) || name.startsWith("docker")) return "docker";
  if (CI_NAMES.some((marker) => name === marker || name.endsWith(marker))) return "ci";
  if (TEST_MARKERS.some((marker) => name.includes(marker))) return "test";
  return null;
}

function SignalChip({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className={`chip ${ok ? "ok" : "missing"}`}>
      {label} {ok ? "✓" : "✗"}
    </span>
  );
}

export default function FileTreeExplorer({ projectId }: { projectId: string | number }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<ProjectTree | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && !data && !loading) {
      setLoading(true);
      setError("");
      try {
        setData(await api.getProjectTree(projectId));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load project files");
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <section className="file-tree-section">
      <div className="file-tree-toggle-row">
        <h2>Project files</h2>
        <button className="ghost" onClick={toggle}>
          {open ? "Hide project files" : "Show project files"}
        </button>
      </div>

      {open && (
        <>
          {loading && <p className="muted">Scanning project…</p>}
          {error && <p className="error">{error}</p>}
          {data && (
            <>
              <div className="signal-legend">
                <SignalChip label="Tests" ok={data.signals.has_tests} />
                <SignalChip label="CI" ok={data.signals.has_ci} />
                <SignalChip label="Docker" ok={data.signals.has_docker} />
                <SignalChip label="Lockfile" ok={data.signals.has_lockfile} />
                <SignalChip label="License" ok={data.signals.has_license} />
              </div>
              <div className="tree-panel">
                {data.tree.split("\n").map((line, i) => {
                  const kind = lineKind(line);
                  return (
                    <div key={i} className={`tree-line ${kind ? `tree-${kind}` : ""}`}>
                      {line || " "}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
