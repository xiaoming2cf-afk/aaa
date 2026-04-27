import { Activity } from "lucide-react";
import { InlineEmptyState } from "../StatusPrimitives";
import { Badge, MetricPill, Surface } from "../ui";
import { formatValue, gateTone } from "./viewHelpers";

type ArbiterTrendProps = {
  arbiterMode?: string;
  trendChoices: boolean[];
  trendPosteriors: number[];
  v2SampleCount: number;
};

export function ArbiterTrend({
  arbiterMode,
  trendChoices,
  trendPosteriors,
  v2SampleCount,
}: ArbiterTrendProps): JSX.Element {
  return (
    <Surface
      actions={<Badge tone={arbiterMode ? "info" : "neutral"}>{arbiterMode || "off"}</Badge>}
      className="ops-col-5"
      description="Recent delivery posteriors and choices from the ARBITER delivery layer."
      eyebrow="ARBITER"
      title={<><Activity aria-hidden="true" size={18} /> Delivery Mini Trend</>}
    >
      <div className="metric-strip">
        <MetricPill label="Latest posterior" value={trendPosteriors.length ? formatValue(trendPosteriors[trendPosteriors.length - 1]) : "-"} />
        <MetricPill label="V2 samples" value={v2SampleCount} />
        <MetricPill label="Choices" value={trendChoices.length || 0} />
      </div>
      <p className="muted">Recent delivery posteriors: {trendPosteriors.length ? trendPosteriors.map((item) => item.toFixed(3)).join(", ") : "none"}</p>
      <p className="muted">Recent v2 posteriors: {trendPosteriors.length ? trendPosteriors.map((item) => item.toFixed(3)).join(", ") : "none"}</p>
      {trendPosteriors.length ? (
        <div className="timeline">
          {trendPosteriors.map((posterior, index) => {
            const choice = trendChoices[index];
            const choiceState = choice === true ? true : choice === false ? false : undefined;
            return (
              <div key={`${posterior}-${index}`} className="timeline-item">
                <span className="timeline-dot" aria-hidden="true" />
                <div>
                  <div className="list-card-title">
                    <strong>Sample {index + 1}</strong>
                    <Badge tone={gateTone(choiceState)}>{choice === true ? "deliver" : choice === false ? "block" : "unknown"}</Badge>
                  </div>
                  <p className="muted">posterior {formatValue(posterior)}</p>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <InlineEmptyState title="No ARBITER trend yet" description="Recent delivery posteriors will appear after reviewed runs persist ARBITER metadata." />
      )}
    </Surface>
  );
}
