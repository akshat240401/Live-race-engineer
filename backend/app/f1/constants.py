from enum import IntEnum


class PacketId(IntEnum):
    MOTION = 0
    SESSION = 1
    LAP_DATA = 2
    EVENT = 3
    PARTICIPANTS = 4
    CAR_SETUPS = 5
    CAR_TELEMETRY = 6
    CAR_STATUS = 7
    FINAL_CLASSIFICATION = 8
    LOBBY_INFO = 9
    CAR_DAMAGE = 10
    SESSION_HISTORY = 11
    TYRE_SETS = 12
    MOTION_EX = 13
    TIME_TRIAL = 14
    LAP_POSITIONS = 15
    CAR_TELEMETRY_2 = 16  # 2026 Season Pack


PACKET_NAMES = {
    PacketId.MOTION: "motion",
    PacketId.SESSION: "session",
    PacketId.LAP_DATA: "lap_data",
    PacketId.EVENT: "event",
    PacketId.PARTICIPANTS: "participants",
    PacketId.CAR_SETUPS: "car_setups",
    PacketId.CAR_TELEMETRY: "car_telemetry",
    PacketId.CAR_STATUS: "car_status",
    PacketId.FINAL_CLASSIFICATION: "final_classification",
    PacketId.LOBBY_INFO: "lobby_info",
    PacketId.CAR_DAMAGE: "car_damage",
    PacketId.SESSION_HISTORY: "session_history",
    PacketId.TYRE_SETS: "tyre_sets",
    PacketId.MOTION_EX: "motion_ex",
    PacketId.TIME_TRIAL: "time_trial",
    PacketId.LAP_POSITIONS: "lap_positions",
    PacketId.CAR_TELEMETRY_2: "car_telemetry_2",
}

TYRE_COMPOUNDS = {
    7: "INTER",
    8: "WET",
    16: "SOFT",
    17: "MEDIUM",
    18: "HARD",
    19: "C2/SS",
    20: "C1/S",
    21: "C0/M",
    22: "C6/H",
}
