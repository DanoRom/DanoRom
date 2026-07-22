"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, Evaluation, ProjectDetail } from "@/lib/api";
import Markdown from "@/components/Markdown";

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [learning, setLearning] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadLearning = useCallback((stage: string) => {
    if (!stage || stage === "unevaluated") return;
    api
      .getLearning(stage)
      .then((res) => setLearning(res.markdown))
      .catch(() => setLearning(""));
  }, []);

  useEffect(() => {
    api
      .getProject(id)
      .then((p) => {
        setProject(p);
        setEvaluation(p.latest_evaluation);
        loadLearning(p.stage);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load project"));
  }, [id, loadLearning]);

  const evaluate = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await api.evaluateProject(id);
      setEvaluation(result);
      setProject((p) => (p ? { ...p, stage: result.stage } : p));
      loadLearning(result.stage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Evaluation failed");
    } finally {
      setBusy(false);
    }
  };

  if (error && !project) {
    return (
      <main className="page">
        <p className="error">{error}</p>
        <Link href="/" className="muted">← Back to dashboard</Link>
      </main>
    );
  }
  if (!project) {
    return (
      <main className="page">
        <p className="muted">Loading…</p>
      </main>
    );
  }

  return (
    <main className="page">
      <Link href="/" className="muted">← Back to dashboard</Link>
      <h1 style={{ marginTop: "0.75rem" }}>{project.name}</h1>
      <p className="subtitle">
        {project.description || "No description."}{" "}
        <span className="badge" style={{ marginLeft: "0.5rem" }}>{project.stage}</span>
      </p>

      <button className="cta" onClick={evaluate} disabled={busy}>
        {busy ? "Scanning & evaluating…" : evaluation ? "Re-evaluate stage" : "Evaluate build stage"}
      </button>
      {error && <p className="error">{error}</p>}

      {evaluation && (
        <>
          <div className="card" style={{ marginTop: "1.5rem" }}>
            <h2>Stage assessment</h2>
            <p>
              <strong>{evaluation.stage}</strong> · {evaluation.confidence}% confidence ·
              engine: {evaluation.engine}
            </p>
            <p style={{ marginBottom: 0 }}>{evaluation.summary}</p>
          </div>

          <h2 style={{ marginTop: "2rem" }}>Branching pathways</h2>
          <p className="muted">Next logical development actions, branched by direction.</p>
          <div className="trunk" style={{ marginTop: "1rem" }}>
            <span className="badge red">You are here: {evaluation.stage}</span>
          </div>
          <div className="pathways">
            {evaluation.branches.map((branch, i) => (
              <div key={i} className={`branch ${branch.priority === "critical" ? "critical" : ""}`}>
                <div className="branch-title">
                  {branch.title}{" "}
                  <span className="badge" style={{ float: "right" }}>{branch.priority}</span>
                </div>
                <div className="branch-desc">{branch.description}</div>
                {branch.steps.map((step, j) => (
                  <div key={j} className="step">
                    <strong>{j + 1}. {step.title}</strong>
                    {step.detail && <div className="detail">{step.detail}</div>}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </>
      )}

      {learning && (
        <div className="learning">
          <span className="badge red">Learning Center</span>
          <Markdown source={learning} />
        </div>
      )}
    </main>
  );
}
