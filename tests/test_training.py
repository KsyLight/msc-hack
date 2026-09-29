import pandas as pd
import pytest
from backend.ml.contracts import validate_features
from backend.ml.training import validate_splits, matrix, select_threshold
from scripts.run_notebook import preflight


@pytest.mark.parametrize("feature", ["target_fault_24_48h", "last_seen", "channel_followup_48h", "global_complete_24_48h", "channel_id", "sample_weight"])
def test_future_columns_and_identifiers_rejected(feature):
    with pytest.raises(ValueError):
        validate_features(["events_7d", feature])


def test_temporal_purge_blocks_target_leakage():
    def frame(day):
        return pd.DataFrame({"entity_id": ["a", "b"], "prediction_time": pd.to_datetime([day, day]), "y": [0, 1]})
    splits = {"train": frame("2024-12-31"), "validation": frame("2025-01-01"), "test": frame("2026-01-01")}
    with pytest.raises(ValueError, match="overlap"):
        validate_splits(splits, "y")
    splits["train"] = frame("2024-12-30")
    validate_splits(splits, "y")
    splits["validation"].loc[0, "y"] = None
    with pytest.raises(ValueError, match="censored"):
        validate_splits(splits, "y")


def test_missing_feature_not_silently_replaced_with_zero():
    with pytest.raises(ValueError, match="Missing required"):
        matrix(pd.DataFrame({"events_1d": [4]}), ["events_7d"])
    assert pd.isna(matrix(pd.DataFrame({"events_1d": [None]}), ["events_1d"]).iloc[0, 0])


def test_threshold_selected_from_validation():
    assert .2 < select_threshold([0, 0, 1, 1], [.1, .2, .8, .9]) <= .8


def test_notebook_preflight_reports_all_missing_sources(tmp_path):
    assert len(preflight(tmp_path)) == 11
