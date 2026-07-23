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

  const reupload = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      await api.reuploadProject(id, file);
      const result = await api.evaluateProject(id);
      setEvaluation(result);
      setProject((p) => (p ? { ...p, stage: result.stage, source_type: "upload" } : p));
      loadLearning(result.stage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Re-upload failed");
    } finally {
      setBusy(false);
    }
  };

  const choosePath = async (branchIndex: number) => {
    setBusy(true);
    setError("");
    try {
      setEvaluation(await api.choosePathway(id, branchIndex));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to choose pathway");
    } finally {
      setBusy(false);
    }
  };

  const toggleStep = async (stepIndex: number, done: boolean) => {
    setError("");
    try {
      setEvaluation(await api.updateStep(id, stepIndex, done));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update step");
    }
  };

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

      <div className="action-row">
        <button className="cta" onClick={evaluate} disabled={busy}>
          {busy ? "Scanning & evaluating…" : evaluation ? "Re-evaluate stage" : "Evaluate build stage"}
        </button>
        <label className="ghost upload-label">
          {busy ? "Working…" : "⬆ Upload updated .zip & re-evaluate"}
          <input
            type="file"
            accept=".zip"
            hidden
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) reupload(f);
              e.target.value = "";
            }}
          />
        </label>
      </div>
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
          <p className="muted">
            {evaluation.chosen_branch < 0
              ? "Pick a path — it becomes your active checklist."
              : "Work through your chosen path, then continue to the next evaluation."}
          </p>
          <div className="trunk" style={{ marginTop: "1rem" }}>
            <span className="badge red">You are here: {evaluation.stage}</span>
          </div>
          <div className="pathways">
            {evaluation.branches.map((branch, i) => {
              const isChosen = evaluation.chosen_branch === i;
              const dimmed = evaluation.chosen_branch >= 0 && !isChosen;
              return (
                <div
                  key={i}
                  className={[
                    "branch",
                    branch.priority === "critical" ? "critical" : "",
                    isChosen ? "chosen" : "",
                    dimmed ? "dimmed" : "",
                  ].join(" ")}
                >
                  <div className="branch-title">
                    {branch.title}{" "}
                    <span className="badge" style={{ float: "right" }}>
                      {isChosen ? "active path" : branch.priority}
                    </span>
                  </div>
                  <div className="branch-desc">{branch.description}</div>
                  {branch.steps.map((step, j) => {
                    const done = isChosen && evaluation.completed_steps.includes(j);
                    return isChosen ? (
                      <label key={j} className={`step clickable ${done ? "done" : ""}`}>
                        <input
                          type="checkbox"
                          checked={done}
                          onChange={(e) => toggleStep(j, e.target.checked)}
                        />
                        <span>
                          <strong>{j + 1}. {step.title}</strong>
                          {step.detail && <div className="detail">{step.detail}</div>}
                        </span>
                      </label>
                    ) : (
                      <div key={j} className="step">
                        <strong>{j + 1}. {step.title}</strong>
                        {step.detail && <div className="detail">{step.detail}</div>}
                      </div>
                    );
                  })}
                  {!isChosen && (
                    <button className="cta full" onClick={() => choosePath(i)} disabled={busy}>
                      {dimmed ? "Switch to this path" : "Choose this path"}
                    </button>
                  )}
                  {isChosen && (
                    <PathProgress
                      total={branch.steps.length}
                      done={evaluation.completed_steps.length}
                      busy={busy}
                      onContinue={evaluate}
                    />
                  )}
                </div>
              );
            })}
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

function PathProgress({
  total,
  done,
  busy,
  onContinue,
}: {
  total: number;
  done: number;
  busy: boolean;
  onContinue: () => void;
}) {
  const complete = total > 0 && done >= total;
  return (
    <div className="path-progress">
      <div className="progress-track">
        <div
          className="progress-fill"
          style={{ width: `${total ? (done / total) * 100 : 0}%` }}
        />
      </div>
      <div className="muted" style={{ fontSize: "0.8rem", margin: "0.4rem 0 0.7rem" }}>
        {done} / {total} steps complete
      </div>
      {complete ? (
        <button className="cta full" onClick={onContinue} disabled={busy}>
          {busy ? "Re-evaluating…" : "Continue → next evaluation"}
        </button>
      ) : (
        <p className="muted" style={{ fontSize: "0.8rem" }}>
          Check off every step to unlock the next evaluation.
        </p>
      )}
    </div>
  );
}
