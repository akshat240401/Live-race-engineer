export type EngineerMessage = {
  id: number;
  timestamp: number;
  severity:
    | "info"
    | "warning"
    | "danger"
    | "success"
    | string;
  category: string;
  title: string;
  message: string;
  evidence: Record<string, unknown>;
};

export type RaceEvent = {
  id: number;
  timestamp: number;
  session_time: number;
  lap_number: number;
  event_type: string;
  severity: string;
  title: string;
  description: string;
  data: Record<string, unknown>;
};

export type CarRaceState = {
  car_index: number;
  name: string;
  position: number;
  lap_number: number;
  lap_distance_m: number;
  total_distance_m: number;
  current_lap_time_ms: number;
  last_lap_time_ms: number;
  delta_to_leader_s: number;
  delta_to_car_ahead_s: number;
  pit_status: number;
  pit_stops: number;
  grid_position: number;
  driver_status: number;
  result_status: number;
  penalties_s: number;
  team_id?: number | null;
  driver_id?: number | null;
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
  position: number;
  ers_percent: number;
  fuel_remaining_laps: number;
  tyre_wear_pct: number[];
  tyre_surface_temps_c: number[];
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
  session_uid: number | null;
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
  total_laps: number;
  current_lap_time_ms: number;
  last_lap_time_ms: number;
  best_lap_time_ms: number | null;
  lap_distance_m: number;
  total_distance_m: number;
  track_length_m: number | null;
  track_id: number | null;
  session_type: number | null;

  position: number;
  grid_position: number;
  grid_size: number;
  positions_gained: number;
  sector: number;
  lap_invalid: boolean;
  warnings: number;
  penalties_s: number;
  pit_status: number;
  pit_stops: number;
  driver_status: number;
  result_status: number;
  delta_to_car_ahead_s: number;
  delta_to_leader_s: number;

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

  wing_damage_pct: {
    fl: number;
    fr: number;
    rear: number;
  };

  world_position: number[];
  world_velocity: number[];
  g_force_lateral: number;
  g_force_longitudinal: number;

  player_name: string;
  car_ahead: CarRaceState | null;
  car_behind: CarRaceState | null;
  leader: CarRaceState | null;
  classification: CarRaceState[];

  active_session_id: string | null;
  recording_enabled: boolean;

  completed_laps: Array<
    Record<string, unknown>
  >;

  recent_messages: EngineerMessage[];
  race_events: RaceEvent[];
  history: HistoryPoint[];
  track_points: TrackPoint[];
};

export type ControlState = {
  voice_enabled: boolean;
  coaching_enabled: boolean;
  recording_enabled?: boolean;
  active_session_id?: string | null;
  udp_running?: boolean;
  last_voice_error?: string | null;
  last_udp_error?: string | null;
  llm_enabled?: boolean;
};

export type SessionListItem = {
  session_id: string;
  started_at: string | null;
  ended_at: string | null;
  status: string;
  track_id: number | null;
  session_type: number | null;
  total_laps: number;
  finish_position: number | null;
  recorded_samples: number;
  has_report: boolean;
};

export type PostRaceSummary = {
  player_name: string;
  track_id: number | null;
  session_type: number | null;
  start_position: number | null;
  finish_position: number | null;
  positions_gained: number | null;
  completed_laps: number;
  valid_laps: number;
  best_lap_s: number | null;
  average_lap_s: number | null;
  median_lap_s: number | null;
  lap_consistency_s: number | null;
  overtakes_detected: number;
  positions_lost_detected: number;
  incidents_detected: number;
  penalties_detected: number;
  brake_throttle_overlap_s: number;
  max_tyre_wear_pct: number;
  max_tyre_temp_c: number;
  max_brake_temp_c: number;
  fuel_used_kg: number;
  recorded_samples: number;
  pace_trend: string;
};

export type PostRaceReport = {
  session_id: string;
  generated_from: string;
  summary: PostRaceSummary;
  strengths: string[];
  areas_to_improve: string[];
  lap_analysis: Array<
    Record<string, unknown>
  >;
  timeline: RaceEvent[];
  coaching_messages: EngineerMessage[];
  classification: Array<
    Record<string, unknown>
  >;
  comparisons: Record<
    string,
    Record<string, unknown> | null
  >;
};

export type AIReport = {
  session_id: string;
  question: string;
  provider: string;
  llm_error: string | null;
  narrative: string;
  retrieved_context: Array<{
    id: string;
    kind: string;
    score: number;
    text: string;
  }>;
  grounded_summary: PostRaceSummary;
};