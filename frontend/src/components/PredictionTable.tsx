import { ChevronRight, Radio, Wrench } from "lucide-react";
import { Prediction, date, labels, riskLabels, score } from "../api";

export default function PredictionTable({
  rows,
  onSelect,
  loading = false,
}: {
  rows: Prediction[];
  onSelect: (r: Prediction) => void;
  loading?: boolean;
}) {
  if (loading) return <div className="empty">Загружаем прогнозы…</div>;
  if (!rows.length)
    return <div className="empty">По выбранным фильтрам прогнозов нет.</div>;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Объект / канал</th>
            <th>Направление</th>
            <th>Уровень риска</th>
            <th>Оценка / 100</th>
            <th>Период прогноза</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              tabIndex={0}
              aria-label={`${r.object_name}, ${labels[r.direction]}, ${riskLabels[r.risk]}`}
              onClick={() => onSelect(r)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(r);
                }
              }}
            >
              <td>
                <button
                  className="object-link"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect(r);
                  }}
                >
                  {r.object_name}
                </button>
                <small>
                  {r.entity_id} · {r.sensor_type}
                </small>
                {r.system_type && <small>{r.system_type}</small>}
              </td>
              <td>
                <span className="direction-cell">
                  {r.direction === "sensor" ? (
                    <Radio size={14} />
                  ) : (
                    <Wrench size={14} />
                  )}{" "}
                  {labels[r.direction]}
                </span>
              </td>
              <td>
                <span className={`badge ${r.risk}`}>
                  <i />
                  {riskLabels[r.risk]}
                </span>
              </td>
              <td>
                <div className="score">
                  <strong>{score(r.score)}</strong>
                  <span>
                    <i
                      style={{ width: `${(r.score ?? 0) * 100}%` }}
                      className={r.risk}
                    />
                  </span>
                </div>
              </td>
              <td className="nowrap">
                {date(r.target_start)} — {date(r.target_end)}
              </td>
              <td>
                <ChevronRight size={16} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
