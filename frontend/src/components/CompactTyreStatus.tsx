import type { CSSProperties } from "react";

import styles from "./CompactTyreStatus.module.css";

const LABELS = ["RL", "RR", "FL", "FR"];

function clamp(value: number): number {
  return Math.max(0, Math.min(100, value));
}

export function CompactTyreStatus({
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
    <section className={styles.panel}>
      <header>
        <div>
          <span>Compound</span>
          <strong>{compound || "UNKNOWN"}</strong>
        </div>
        <b>{age}L</b>
      </header>
      <div className={styles.tyres}>
        {LABELS.map((label, index) => {
          const currentWear = clamp(wear[index] || 0);
          const currentTemp = Math.round(temps[index] || 0);
          return (
            <article key={label}>
              <span>{label}</span>
              <div className={styles.ring} style={{ "--wear": `${currentWear * 3.6}deg` } as CSSProperties}>
                <div><strong>{Math.round(currentWear)}</strong><small>%</small></div>
              </div>
              <b>{currentTemp}°</b>
            </article>
          );
        })}
      </div>
    </section>
  );
}