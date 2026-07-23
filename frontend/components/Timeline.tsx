import { Evaluation } from "@/lib/api";

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Timeline({ evaluations }: { evaluations: Evaluation[] }) {
  return (
    <section className="timeline">
      <h2>Progress timeline</h2>
      <p className="muted">Every evaluation, newest first.</p>
      <div className="timeline-list">
        {evaluations.map((evaluation) => (
          <div key={evaluation.id} className="timeline-node">
            <div className="timeline-card">
              <div className="timeline-meta">
                <span>{formatTimestamp(evaluation.created_at)}</span>
                <span className="badge">{evaluation.stage}</span>
                <span>engine: {evaluation.engine}</span>
                <span>{evaluation.confidence}% confidence</span>
              </div>
              {evaluation.changes.length > 0 && (
                <div className="chips-row">
                  {evaluation.changes.map((change, i) => (
                    <span key={i} className="chip">
                      {change}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
