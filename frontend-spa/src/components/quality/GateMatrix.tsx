import { BarChart3 } from "lucide-react";
import { InlineEmptyState } from "../StatusPrimitives";
import { Badge, Surface } from "../ui";
import type { EngineeringGate, GateRow, QualityDimension } from "./types";
import { checkSummary, clampPercent, dimensionGateState, gateLabel, gateTone } from "./viewHelpers";

type GateMatrixProps = {
  dimensions: QualityDimension[];
  engineeringGate?: EngineeringGate;
  engineeringGateState?: boolean;
  gateRows: GateRow[];
  scorecardReady: boolean;
};

export function GateMatrix({
  dimensions,
  engineeringGate,
  engineeringGateState,
  gateRows,
  scorecardReady,
}: GateMatrixProps): JSX.Element {
  return (
    <Surface
      actions={<Badge tone={gateTone(engineeringGateState)}>{scorecardReady ? gateLabel(engineeringGateState) : "Not known"}</Badge>}
      className="ops-col-7"
      description="Each gate stays blocked or unknown until its own source reports a pass."
      eyebrow="Gate Matrix"
      title={<><BarChart3 aria-hidden="true" size={18} /> Gate Matrix</>}
    >
      {scorecardReady ? (
        <div className="gate-matrix">
          {gateRows.map((row) => (
            <div key={row.key}>
              <div className="gate-row">
                <div>
                  <strong>{row.label}</strong>
                  <p className="muted">{row.summary}</p>
                </div>
                <Badge tone={gateTone(row.state)}>{gateLabel(row.state)}</Badge>
              </div>
              <div className="gate-bar" aria-label={`${row.label} score ${row.score ?? "unknown"}`}>
                <span style={{ width: `${clampPercent(row.score ?? 0)}%` }} />
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {scorecardReady && !dimensions.length ? (
        <InlineEmptyState title="No scorecard dimensions yet" description="Run quality scoring to populate delivery dimensions and checks." />
      ) : null}

      {scorecardReady ? (
        <div className="ops-table-scroll">
          <table className="ops-table">
            <thead>
              <tr>
                <th scope="col">Gate</th>
                <th scope="col">State</th>
                <th scope="col">Checks</th>
              </tr>
            </thead>
            <tbody>
              {dimensions.map((dimension) => (
                <tr key={dimension.key}>
                  <td>{dimension.label}</td>
                  <td><Badge tone={gateTone(dimensionGateState(dimension))}>{gateLabel(dimensionGateState(dimension))}</Badge></td>
                  <td>{checkSummary(dimension.checks)}</td>
                </tr>
              ))}
              <tr>
                <td>Engineering Gate</td>
                <td><Badge tone={gateTone(engineeringGateState)}>{gateLabel(engineeringGateState)}</Badge></td>
                <td>{engineeringGate?.checks?.length ? checkSummary(engineeringGate.checks) : "No engineering checks returned."}</td>
              </tr>
            </tbody>
          </table>
        </div>
      ) : (
        <InlineEmptyState title="Gate matrix unavailable" description="Quality unavailable states are reported as UNKNOWN, never PASS." />
      )}
    </Surface>
  );
}
