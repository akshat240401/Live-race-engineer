from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Live Race Engineer"

    udp_host: str = "0.0.0.0"
    udp_port: int = 20777
    enable_udp_listener: bool = True

    enable_voice: bool = True
    enable_coaching: bool = True
    enable_recording: bool = True
    voice_rate: int = 185
    voice_volume: float = 0.85

    history_limit: int = 9000
    recording_sample_hz: float = 5.0
    data_dir: str = "data/sessions"

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Existing OpenAI-compatible post-race LLM settings.
    llm_enabled: bool = False
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_s: int = 45

    # Hands-free radio.
    radio_enabled: bool = True
    radio_mode: str = "race"
    radio_wake_phrases: str = "engineer,race engineer"
    radio_followup_window_s: float = 20.0
    radio_command_timeout_s: float = 8.0
    radio_input_device: str = ""

    # Audio segmentation. The shorter standby timeout makes the wake word
    # acknowledge quickly. The longer command timeout allows natural pauses.
    radio_sample_rate: int = 16000
    radio_frame_ms: int = 30
    radio_vad_aggressiveness: int = 2
    radio_end_silence_ms: int = 700
    radio_command_end_silence_ms: int = 1050
    radio_min_speech_ms: int = 250
    radio_max_utterance_s: float = 15.0
    radio_pre_roll_ms: int = 300
    radio_min_confidence: float = 0.10

    # Optional local noise calibration and energy gate.
    radio_energy_gate_enabled: bool = True
    radio_energy_multiplier: float = 1.8
    radio_energy_floor_rms: int = 90
    radio_noise_calibration_s: float = 5.0

    radio_stt_model: str = "base.en"
    radio_stt_device: str = "auto"
    radio_stt_compute_type: str = "int8"
    radio_language: str = "en"
    radio_preload_stt: bool = True

    # Wake acknowledgement: beep, voice, both, or silent.
    radio_ack_mode: str = "beep"
    radio_ack_text: str = "Listening."
    radio_ack_beep_frequency_hz: int = 920
    radio_ack_beep_duration_ms: int = 95

    # Response shaping.
    radio_response_style: str = "concise"
    radio_max_response_words: int = 24

    # Automatic call control.
    radio_min_auto_message_interval_s: float = 10.0
    radio_duplicate_cooldown_s: float = 45.0
    radio_category_cooldown_s: float = 20.0
    radio_critical_override: bool = True
    radio_corner_safe_delivery: bool = True
    radio_pending_message_max_wait_s: float = 8.0

    radio_barge_in_enabled: bool = False
    radio_echo_similarity: float = 0.72
    radio_transcript_limit: int = 120
    radio_profile_path: str = "data/radio_profile.json"
    radio_log_dir: str = "data/radio_logs"

    # Ask for confirmation before muting automatic calls through voice.
    radio_confirm_control_actions: bool = True

    # Live LLM is optional. It reuses the LLM endpoint/model above.
    live_llm_enabled: bool = False
    live_llm_max_words: int = 32

    # Unified live strategy, battle, ERS and coaching engine.
    strategy_enabled: bool = True
    strategy_evaluation_interval_s: float = 0.75
    strategy_default_pit_loss_s: float = 22.0
    strategy_default_lap_time_s: float = 90.0

    strategy_critical_wear_pct: float = 82.0
    strategy_box_wear_pct: float = 68.0
    strategy_marginal_finish_wear_pct: float = 78.0
    strategy_max_finish_wear_pct: float = 90.0
    strategy_hot_tyre_c: float = 108.0
    strategy_critical_tyre_c: float = 115.0

    strategy_attack_gap_s: float = 1.6
    strategy_defend_gap_s: float = 1.2
    strategy_ers_attack_reserve_pct: float = 28.0
    strategy_ers_defend_reserve_pct: float = 22.0
    strategy_ers_harvest_target_pct: float = 55.0

    strategy_auto_calls: bool = True
    strategy_auto_battle_calls: bool = True
    strategy_auto_box_calls: bool = True
    strategy_auto_ers_calls: bool = True
    strategy_auto_coaching_calls: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
