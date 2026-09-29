export type Direction = "sensor" | "infrastructure" | "smoke";
export type Risk = "high" | "medium" | "low" | "unavailable";
export interface Prediction {
  id: string;
  direction: Direction;
  entity_id: string;
  object_id: string;
  object_name: string;
  sensor_type: string;
  system_type: string;
  sensor_name: string;
  system_tag: string;
  prediction_time: string;
  target_start: string;
  target_end: string;
  score: number | null;
  risk: Risk;
  threshold: number;
  state: string;
  recommendation: string;
  model_version: string;
  mode: string;
  factors: { feature: string; label: string; value: number }[];
}
export interface Dashboard {
  mode: string;
  as_of: string;
  objects: number;
  channels: number;
  high_risk: number;
  open_tickets: number;
  unavailable: number;
  directions: Record<Direction, { total: number; high: number }>;
  trend: {
    date: string;
    sensor: number;
    infrastructure: number;
    smoke?: number;
    total: number;
  }[];
  top_predictions: Prediction[];
  observations: {
    date: string;
    events: number | null;
    alarms: number | null;
    fault_messages: number | null;
    sensor: number | null;
    infrastructure: number | null;
    active_channels: number | null;
  }[];
}
export interface Collector {
  id: string;
  name: string;
  district: string;
  latitude: number | null;
  longitude: number | null;
  coordinate_source: string;
  channels: number;
  high_risk: number;
  max_score: number | null;
}
export interface Metrics {
  precision: number;
  recall: number;
  pr_auc: number;
  rows: number;
  positives: number;
  false_positives: number;
}
export interface Model {
  direction: Direction;
  algorithm: string;
  version: string;
  provenance: string;
  threshold: number;
  test: Metrics;
  meets_case_metrics: boolean;
  features: string[];
  training_seconds: number;
  validation_candidates: (Metrics & { algorithm: string })[];
}
export interface Quality {
  mode: string;
  provenance: string;
  notice: string;
  snapshot_time: string;
  scoring_rows: number;
  eligible_rows: number;
  unavailable_rows: number;
  limitations: string[];
  source_snapshot_channels?: number;
  excluded_snapshot_channels?: number;
  missing_channel_metadata?: number;
  missing_object_metadata?: number;
  coverage?: {
    direction: Direction;
    sensor_type: string;
    channels: number;
    eligible: number;
  }[];
  observations?: {
    start: string;
    end: string;
    days: number;
    events: number;
    alarms: number;
    fault_messages: number;
    missing_days: string[];
    unmapped_channel_days: number;
  };
}
export interface Ticket {
  id: number;
  prediction_id: string;
  status: string;
  comment: string;
  created_at: string;
  automatic: number;
  prediction: Prediction;
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Ошибка запроса (${response.status})`,
    );
  }
  return response.json();
}
export const labels: Record<Direction, string> = {
  sensor: "Отказ датчика",
  infrastructure: "Инфраструктура",
  smoke: "Сигнал дыма",
};
export const riskLabels: Record<Risk, string> = {
  high: "Высокий",
  medium: "Внимание",
  low: "Низкий",
  unavailable: "Нет оценки",
};
export const score = (value: number | null) =>
  value === null ? "—" : (value * 100).toFixed(1);
export const date = (value: string) =>
  new Date(value).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "short",
  });
