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

export type RadioMode =
  | "minimal"
  | "race"
  | "coaching";

export type RadioState =
  | "disabled"
  | "starting"
  | "standby"
  | "listening"
  | "transcribing"
  | "thinking"
  | "speaking"
  | "calibrating"
  | "error";

export type RadioStatus = {
  enabled: boolean;
  running: boolean;
  state: RadioState;
  mode: RadioMode;
  muted: boolean;
  conversation_open: boolean;
  awaiting_command: boolean;
  command_timeout_s: number;
  command_time_remaining_s: number;
  wake_phrases: string[];
  input_device: string | number | null;
  input_device_name: string | null;
  stt_model: string;
  stt_ready: boolean;
  llm_enabled: boolean;
  barge_in_enabled: boolean;
  ack_mode: "beep" | "voice" | "both" | "silent" | string;
  response_style: "concise" | "normal" | "detailed" | string;
  noise_floor_rms: number;
  calibrating: boolean;
  calibration_remaining_s: number;
  pending_auto_messages: number;
  pending_confirmation: string | null;
  last_heard: string | null;
  last_normalized: string | null;
  last_response: string | null;
  last_error: string | null;
  last_activity_at: number | null;
  transcript_count: number;
  timestamp?: number;
};

export type RadioTranscriptEntry = {
  id: number;
  timestamp: number;
  speaker: "driver" | "engineer" | "system" | string;
  text: string;
  source: string;
  topic: string | null;
  confidence: number | null;
  priority: number;
  metadata: Record<string, unknown>;
};

export type AudioInputDevice = {
  index: number;
  name: string;
  max_input_channels: number;
  default_samplerate: number;
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

  completed_laps: Array<Record<string, unknown>>;
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
  live_llm_enabled?: boolean;
  radio_enabled?: boolean;
  radio_state?: RadioState;
  radio_mode?: RadioMode;
  radio?: RadioStatus;
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
  lap_analysis: Array<Record<string, unknown>>;
  timeline: RaceEvent[];
  coaching_messages: EngineerMessage[];
  classification: Array<Record<string, unknown>>;
  comparisons: Record<string, Record<string, unknown> | null>;
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

export type BattleState =
  | "critical"
  | "attacking"
  | "defending"
  | "managing"
  | "clear_air"
  | "pit_window"
  | "unknown";

export type BoxAction =
  | "box_now"
  | "stay_out"
  | "conditional"
  | "already_boxing"
  | "unknown";

export type EnergyAction =
  | "deploy"
  | "save_then_deploy"
  | "defend"
  | "harvest"
  | "balanced"
  | "critical"
  | "unknown";

export type NearbyCarAssessment = {
  role: "ahead" | "behind" | string;
  name: string;
  position: number | null;
  gap_s: number | null;
  gap_trend_s_per_lap: number | null;
  relative_last_lap_s: number | null;
  in_drs_range: boolean;
  pit_status: number;
  pit_stops: number;
  assessment: string;
};

export type TyreProjection = {
  compound: string;
  age_laps: number;
  max_wear_pct: number;
  average_wear_pct: number;
  hottest_temp_c: number;
  wear_per_lap_pct: number;
  laps_remaining: number | null;
  projected_finish_wear_pct: number | null;
  can_finish: boolean | null;
  status: string;
  confidence: number;
};

export type BoxDecision = {
  action: BoxAction;
  confidence: number;
  summary: string;
  reason_codes: string[];
  expected_rejoin_position: number | null;
  estimated_positions_lost: number | null;
  traffic_cars: string[];
  estimated_pit_loss_s: number | null;
  undercut_opportunity: boolean;
  overcut_opportunity: boolean;
};

export type EnergyPlan = {
  action: EnergyAction;
  battery_percent: number;
  target_percent: number;
  minimum_reserve_percent: number;
  deployment_zone: string;
  summary: string;
  confidence: number;
};

export type CoachingPlan = {
  focus: string;
  summary: string;
  severity: string;
  confidence: number;
};

export type LiveRaceDecision = {
  generated_at: number;
  connected: boolean;
  battle_state: BattleState;
  position: number | null;
  lap_number: number | null;
  total_laps: number | null;
  laps_remaining: number | null;
  car_ahead: NearbyCarAssessment | null;
  car_behind: NearbyCarAssessment | null;
  tyres: TyreProjection;
  box: BoxDecision;
  energy: EnergyPlan;
  coaching: CoachingPlan;
  data_quality: number;
  reason_codes: string[];
};
