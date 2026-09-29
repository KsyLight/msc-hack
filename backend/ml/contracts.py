import re

SENSOR_FEATURES = [
    "events_1d", "events_7d", "events_30d", "alarms_7d",
    "fault_messages_30d", "undefined_messages_7d", "disabled_messages_7d",
    "hours_since_last_event", "alarm_rate_7d", "event_ratio_1d_7d",
    "active_days_30d", "history_complete_days",
]
SENSOR_PATTERN = r"контакт|объ[её]мн|температур|дым|газ"
INFRASTRUCTURE_PATTERN = r"состояние насоса|состояние вентилятора"
TARGETS = {"sensor": "target_fault_24_48h", "infrastructure": "target_fault_24_48h"}
LABELS = {"sensor": "Отказ датчика", "infrastructure": "Состояние инфраструктуры"}


def validate_features(features: list[str]):
    forbidden = {"channel_id", "entity_id", "object_id", "sensor_type", "system_type", "object_id_current", "sensor_type_current", "system_type_current",
                 "prediction_time", "target_end", "target_start", "last_seen", "first_seen",
                 "channel_followup_48h", "global_complete_24_48h", "sample_weight",
                 "sampling_probability", "at_risk_with_history", "feature_max_ts", "last_state_ts", "global_complete_0_24h"}
    if not features or len(features) != len(set(features)):
        raise ValueError("Feature list must be nonempty and unique")
    if any(f in forbidden or f.startswith("target_") or not re.fullmatch(r"[a-z][a-z0-9_]*", f) for f in features):
        raise ValueError("Feature contract contains metadata, a target or future information")
