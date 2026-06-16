const tyreNames = ["RL", "RR", "FL", "FR"];

function stateForWear(wear: number): "ok" | "warn" | "danger" {
  if (wear >= 65) return "danger";
  if (wear >= 35) return "warn";
  return "ok";
}

export function TyrePanel({
  temps,
  wear,
  compound,
  age,
}: {
  temps: number[];
  wear: number[];
  compound: string;
  age: number;
}) {
  return (
    <div className="panel">
      <div className="tyre-top">
        <h3>Tyres</h3>
        <span className="compound">{compound || "UNKNOWN"}</span>
      </div>

      <div className="tyre-age">stint age: {age} laps</div>

      <div className="tyre-grid">
        {tyreNames.map((name, index) => {
          const tyreWear = Math.round(wear[index] || 0);
          const tyreTemp = Math.round(temps[index] || 0);

          return (
            <div className={`tyre-box ${stateForWear(tyreWear)}`} key={name}>
              <div className="tyre-name">{name}</div>
              <div className="tyre-wear">{tyreWear}%</div>
              <div className="tyre-temp">{tyreTemp} °C</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}