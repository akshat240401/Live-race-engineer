export type EngineerMessage = {
  id: number;
  timestamp: number;
  severity: "info" | "warning" | "danger" | "success" | string;
  category: string;
  title: string;
  message: string;
  evidence: Record<string, unknown>;
};

export type TrackPoint = {
  t: number;
  session_time: number;
  lap_number: number;
  lap_distance_m: number;
  x: number;
  y: number;
  z: number;
  speed_kph: number;
};

export type HistoryPoint = {
  t: number;
  session_time: number;
  speed_kph: number;
  throttle: number;
  brake: number;
  steer: number;
  gear: number;
  rpm: number;
  lap_distance_m: number;
  lap_number: number;
  ers_percent: number;
  fuel_remaining_laps: number;
  world_position: number[];
  world_velocity: number[];
  g_force_lateral: number;
  g_force_longitudinal: number;
};

export type TelemetrySnapshot = {
  connected: boolean;
  packet_count: number;
  last_packet_age_s: number | null;
  packet_format: number | null;
  game_year: number | null;
  session_time: number;
  frame: number;

  speed_kph: number;
  throttle: number;
  brake: number;
  steer: number;
  gear: number;
  rpm: number;
  drs: boolean;
  rev_lights_percent: number;

  lap_number: number;
  current_lap_time_ms: number;
  last_lap_time_ms: number;
  best_lap_time_ms: number | null;
  lap_distance_m: number;
  track_length_m: number | null;
  track_id: number | null;
  position: number;
  sector: number;
  lap_invalid: boolean;
  warnings: number;
  penalties_s: number;

  fuel_remaining_laps: number;
  fuel_in_tank_kg: number;
  ers_store_j: number;
  ers_percent: number;
  ers_deploy_mode: number;
  drs_allowed: boolean;
  drs_activation_distance_m: number;
  tyre_age_laps: number;
  tyre_compound: string;
  front_brake_bias: number;
  traction_control: number;
  abs_enabled: boolean;

  brake_temps_c: number[];
  tyre_surface_temps_c: number[];
  tyre_inner_temps_c: number[];
  tyre_pressures_psi: number[];
  tyre_wear_pct: number[];
  tyre_damage_pct: number[];
  wing_damage_pct: { fl: number; fr: number; rear: number };

  world_position: number[];
  world_velocity: number[];
  g_force_lateral: number;
  g_force_longitudinal: number;

  completed_laps: Array<Record<string, unknown>>;
  recent_messages: EngineerMessage[];
  history: HistoryPoint[];
  track_points: TrackPoint[];
};

export type ControlState = {
  voice_enabled: boolean;
  coaching_enabled: boolean;
  udp_running?: boolean;
  last_voice_error?: string | null;
  last_udp_error?: string | null;
};