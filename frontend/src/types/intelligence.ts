export type ForecastPoint = {
  horizon_laps: number;
  ahead_gap_s: number | null;
  ahead_low_s: number | null;
  ahead_high_s: number | null;
  ahead_drs_probability: number | null;
  behind_gap_s: number | null;
  behind_low_s: number | null;
  behind_high_s: number | null;
  behind_drs_probability: number | null;
};

export type RivalModel = {
  role: "ahead" | "behind" | string;
  name: string;
  position: number | null;
  current_gap_s: number | null;
  predicted_gap_next_lap_s: number | null;
  gap_trend_s_per_lap: number | null;
  closing_probability: number;
  drs_probability_next_lap: number;
  pressure_score: number;
  consistency_score: number;
  predictability_score: number;
  sample_count: number;
  model_quality: number;
  pit_status: number;
  pit_stops: number;
};

export type RelativePace = {
  ahead_s_per_lap: number | null;
  behind_s_per_lap: number | null;
  ahead_confidence: number;
  behind_confidence: number;
};

export type BattleProbabilities = {
  attack: number;
  defend: number;
  contested: number;
  clear: number;
};

export type DecisionEvent = {
  timestamp: number;
  session_time: number;
  lap_number: number | null;
  state: string;
  target: string | null;
  confidence: number;
};

export type ModelMeta = {
  name: string;
  method: string;
  session_uid: number | null;
  sample_count: number;
  effective_sample_count: number;
  lap_time_estimate_s: number | null;
  data_quality: number;
  drs_window_s: number;
  state_confidence_z: number;
};

export type BattleIntelligence = {
  generated_at: number;
  connected: boolean;
  state: "attack" | "defend" | "contested" | "clear" | "observe" | string;
  target: string | null;
  target_role: "ahead" | "behind" | null | string;
  confidence: number;
  decision_resolved: boolean;
  state_margin: number;
  dominant_probability: number;
  runner_up_probability: number;
  window_laps: number | null;
  probabilities: BattleProbabilities;
  ahead: RivalModel | null;
  behind: RivalModel | null;
  relative_pace: RelativePace;
  forecast: ForecastPoint[];
  timeline: DecisionEvent[];
  model: ModelMeta | null;
};
