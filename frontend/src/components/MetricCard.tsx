type Props = {
  label: string;
  value: string | number;
  sub?: string;
};

export function MetricCard({ label, value, sub }: Props) {
  return (
    <div className="metric-card">
      <div>
        <div className="metric-label">{label}</div>
        <div className="metric-value">{value}</div>
      </div>

      {sub ? <div className="metric-sub">{sub}</div> : null}
    </div>
  );
}