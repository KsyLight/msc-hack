from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

Direction = Literal["sensor", "infrastructure", "smoke"]


class TicketCreate(BaseModel):
    prediction_id: str = Field(min_length=1, max_length=64)
    comment: str = Field(default="", max_length=2000)


class TicketUpdate(BaseModel):
    status: Literal["new", "in_progress", "done", "dismissed"]
    comment: str = Field(default="", max_length=2000)


class PredictionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str = Field(min_length=1, max_length=100)
    object_id: str = Field(min_length=1, max_length=100)
    sensor_type: str = Field(min_length=1, max_length=150)
    system_type: str = Field(default="", max_length=200)
    sensor_name: str = Field(default="", max_length=500)
    system_tag: str = Field(default="", max_length=200)
    prediction_time: datetime
    eligible: bool
    last_explicit_state: str = "unknown"
    features: dict[str, FiniteFloat | None]


class PredictBatch(BaseModel):
    rows: list[PredictionInput] = Field(min_length=1, max_length=1000)


class Factor(BaseModel):
    feature: str
    label: str
    value: float


class Prediction(BaseModel):
    id: str
    direction: Direction
    entity_id: str
    object_id: str
    object_name: str
    sensor_type: str
    system_type: str = ""
    sensor_name: str = ""
    system_tag: str = ""
    prediction_time: datetime
    target_start: datetime
    target_end: datetime
    score: float | None = Field(ge=0, le=1, description="Raw classifier score; not a calibrated incident probability")
    risk: Literal["high", "medium", "low", "unavailable"]
    threshold: float
    model_version: str
    state: str
    factors: list[Factor]
    recommendation: str
    mode: Literal["demo", "real"]


class PredictionPage(BaseModel):
    total: int
    items: list[Prediction]


class BatchResult(BaseModel):
    items: list[Prediction]
    persisted: bool


class TicketRecord(BaseModel):
    id: int
    prediction_id: str
    status: Literal["new", "in_progress", "done", "dismissed"]
    created_at: datetime
    updated_at: datetime
    comment: str
    automatic: int


class TicketDetail(TicketRecord):
    prediction: Prediction


class Collector(BaseModel):
    id: str
    name: str
    district: str
    latitude: float | None
    longitude: float | None
    coordinate_source: str
    channels: int
    high_risk: int
    max_score: float | None
