"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, Evaluation, LearningContent, ProjectDetail } from "@/lib/api";
import Timeline from "@/components/Timeline";
import FileTreeExplorer from "@/components/FileTreeExplorer";
import LearningCenter from "@/components/LearningCenter";

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [learning, setLearning] = useState<LearningContent | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadLearning = useCallback((stage: string, stack?: string) => {
    if (!stage || stage === "unevaluated") return;
    api
      .getLearning(stage, stack)
      .then((res) => setLearning(res))
      .catch(() => setLearning(null));
  }, []);

  const loadEvaluations = useCallback(() => {
    api
      .listEvaluations(id)
      .then(setEvaluations)
      .catch(() => setEvaluations([]));
  }, [id]);

  useEffect(() => {
    api
      .getProject(id)
      .then((p) => {
        setProject(p);
        setEvaluation(p.latest_evaluation);
        loadLearning(p.stage);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load project"));
    loadEvaluations();
  }, [id, loadLearning, loadEvaluations]);

  const reupload = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      await api.reuploadProject(id, file);
      const result = await api.evaluateProject(id);
      setEvaluation(result);
      setProject((p) => (p ? { ...p, stage: result.stage, source_type: "upload" } : p));
      loadLearning(result.stage);
      loadEvaluations();
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
      loadEvaluations();
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
            <p style={{ marginBottom: evaluation.changes.length ? "0.75rem" : 0 }}>
              {evaluation.summary}
            </p>
            {evaluation.changes.length > 0 && (
              <div>
                <div className="muted" style={{ fontSize: "0.8rem", marginBottom: "0.2rem" }}>
                  What changed since last evaluation
                </div>
                <div className="chips-row">
                  {evaluation.changes.map((change, i) => (
                    <span key={i} className="chip">{change}</span>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "0.75rem",
              marginTop: "2rem",
            }}
          >
            <h2>Branching pathways</h2>
            {evaluation.branches.length > 0 && (
              <button className="ghost" onClick={() => downloadChecklist(project, evaluation)}>
                Export checklist (.md)
              </button>
            )}
          </div>
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

      {evaluations.length >= 1 && <Timeline evaluations={evaluations} />}

      <FileTreeExplorer projectId={id} />

      {learning && (
        <LearningCenter
          learning={learning}
          onSelectStack={(stack) => loadLearning(learning.stage, stack)}
        />
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

function buildChecklistMarkdown(project: ProjectDetail, evaluation: Evaluation): string {
  const lines: string[] = [
    `# ${project.name}`,
    "",
    `**Stage:** ${evaluation.stage}`,
    "",
    evaluation.summary,
  ];

  evaluation.branches.forEach((branch, i) => {
    lines.push("", `## ${branch.title} (${branch.priority})`);
    if (branch.description) lines.push("", branch.description);
    branch.steps.forEach((step, j) => {
      const done = evaluation.chosen_branch === i && evaluation.completed_steps.includes(j);
      const box = done ? "[x]" : "[ ]";
      const detail = step.detail ? ` — ${step.detail}` : "";
      lines.push(`- ${box} ${step.title}${detail}`);
    });
  });

  return lines.join("\n") + "\n";
}

function downloadChecklist(project: ProjectDetail, evaluation: Evaluation) {
  const markdown = buildChecklistMarkdown(project, evaluation);
  const blob = new Blob([markdown], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${project.name.trim().toLowerCase().replace(/\s+/g, "-")}-pathway.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
