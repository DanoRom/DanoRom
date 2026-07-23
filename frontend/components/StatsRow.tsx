import { Stats } from "@/lib/api";

// Cycles through the design-system palette for stage segments beyond the first four.
const STAGE_COLORS = ["#7851a9", "#0000ff", "#ff2800", "#806517"];

export default function StatsRow({ stats }: { stats: Stats }) {
  const stageEntries = Object.entries(stats.stage_counts);
  const totalStaged = stageEntries.reduce((sum, [, count]) => sum + count, 0);

  return (
    <div className="stats-row">
      <div className="card stat-tile">
        <div className="stat-value">{stats.total_projects}</div>
        <div className="stat-label">Projects</div>
      </div>
      <div className="card stat-tile">
        <div className="stat-value">{stats.total_evaluations}</div>
        <div className="stat-label">Evaluations</div>
      </div>
      <div className="card stat-tile">
        <div className="stat-value">{stats.steps_completed}</div>
        <div className="stat-label">Steps completed</div>
      </div>
      <div className="card stat-tile">
        <div className="stat-label" style={{ marginBottom: "0.4rem" }}>
          Stage distribution
        </div>
        {totalStaged > 0 ? (
          <>
            <div className="stage-bar">
              {stageEntries.map(([stage, count], i) => (
                <div
                  key={stage}
                  className="stage-bar-segment"
                  style={{
                    width: `${(count / totalStaged) * 100}%`,
                    background: STAGE_COLORS[i % STAGE_COLORS.length],
                  }}
                  title={`${stage}: ${count}`}
                />
              ))}
            </div>
            <div className="stage-legend">
              {stageEntries.map(([stage, count], i) => (
                <span key={stage} className="stage-legend-item">
                  <span
                    className="stage-legend-swatch"
                    style={{ background: STAGE_COLORS[i % STAGE_COLORS.length] }}
                  />
                  {stage} ({count})
                </span>
              ))}
            </div>
          </>
        ) : (
          <div className="muted" style={{ fontSize: "0.85rem" }}>
            No evaluated projects yet
          </div>
        )}
      </div>
    </div>
  );
}
