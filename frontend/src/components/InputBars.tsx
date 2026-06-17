function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function InputBar({
  label,
  value,
  type,
}: {
  label: string;
  value: number;
  type: "throttle" | "brake";
}) {
  const pct = clamp01(value) * 100;

  return (
    <div className="input-row compact-input-row">
      <div className="input-head">
        <span>{label}</span>
        <span>{pct.toFixed(0)}%</span>
      </div>

      <div className="input-bar">
        <div className={`input-fill ${type}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function Steering({ steer }: { steer: number }) {
  const clamped = Math.max(-1, Math.min(1, steer));
  const left = 50 + clamped * 50;

  return (
    <div className="input-row compact-input-row">
      <div className="input-head">
        <span>Steering</span>
        <span>{(clamped * 100).toFixed(0)}%</span>
      </div>

      <div className="steer-track">
        <div className="steer-mid" />
        <div className="steer-pin" style={{ left: `${left}%` }} />
      </div>
    </div>
  );
}

export function InputBars({
  throttle,
  brake,
  steer,
}: {
  throttle: number;
  brake: number;
  steer: number;
  ers?: number;
}) {
  return (
    <div className="panel compact-inputs-panel">
      <h3>Driver inputs</h3>
      <InputBar label="Throttle" value={throttle} type="throttle" />
      <InputBar label="Brake" value={brake} type="brake" />
      <Steering steer={steer} />
    </div>
  );
}