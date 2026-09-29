import re

SENSOR_FEATURES = [
    "events_1d", "events_7d", "events_30d", "alarms_7d",
    "fault_messages_30d", "undefined_messages_7d", "disabled_messages_7d",
    "hours_since_last_event", "alarm_rate_7d", "event_ratio_1d_7d",
    "active_days_30d", "history_complete_days",
]
SENSOR_PATTERN = r"контакт|объ[её]мн|температур|дым|газ|^кд(?:\s|$)|датчик движения|тепловой датчик"
# Explicit, past-only feature whitelist for the prepared flat Parquet delivery.
HANDOFF_FEATURES = SENSOR_FEATURES + [
    "fault_messages_1d", "fault_messages_7d", "alarms_1d", "alarms_30d",
    "power_messages_1d", "power_messages_7d", "power_messages_30d",
    "undefined_messages_1d", "undefined_messages_30d",
    "disabled_messages_1d", "disabled_messages_30d",
    "event_ratio_7d_30d", "active_days_7d", "night_events_7d", "text_n_7d",
]
INFRASTRUCTURE_PATTERN = r"состояние насоса|состояние вентилятора"
SMOKE_PATTERN = r"дым"
TARGETS = {"sensor": "target_fault_24_48h", "infrastructure": "target_fault_24_48h"}
# Optional third direction; loaded only when runtime/models/smoke.joblib exists.
OPTIONAL_TARGETS = {"smoke": "smoke_signal_24_48h"}
LABELS = {
    "sensor": "Отказ датчика",
    "infrastructure": "Состояние инфраструктуры",
    "smoke": "Сигнал дыма",
}
HORIZONS = {
    "target_fault_24_48h": {"min_hours": 24, "max_hours": 48},
    "target_monthly": {"min_hours": 24, "max_hours": 744},
    "smoke_signal_24_48h": {"min_hours": 24, "max_hours": 48},
}


def validate_features(features: list[str]):
    forbidden = {"channel_id", "entity_id", "object_id", "sensor_type", "system_type", "object_id_current", "sensor_type_current", "system_type_current",
                 "prediction_time", "target_end", "target_start", "last_seen", "first_seen",
                 "channel_followup_48h", "global_complete_24_48h", "sample_weight",
                 "sampling_probability", "at_risk_with_history", "feature_max_ts", "last_state_ts", "global_complete_0_24h"}
    if not features or len(features) != len(set(features)):
        raise ValueError("Feature list must be nonempty and unique")
    if any(f in forbidden or f.startswith("target_") or not re.fullmatch(r"[a-z][a-z0-9_]*", f) for f in features):
        raise ValueError("Feature contract contains metadata, a target or future information")
