import { Database } from "lucide-react";
import { Quality, labels } from "../api";

const fullDate = (value: string) => new Date(value).toLocaleDateString("ru-RU");

export default function DataStatus({ quality }: { quality: Quality }) {
  return (
    <section className="card quality-card">
      <div className="card-heading">
        <div>
          <h3>Доступность прогнозов</h3>
          <p>Состояние каналов на {fullDate(quality.snapshot_time)}</p>
        </div>
        <Database size={24} />
      </div>
      <div className="quality-stats">
        <div>
          <span>Дата данных</span>
          <strong>{fullDate(quality.snapshot_time)}</strong>
        </div>
        <div>
          <span>Каналов</span>
          <strong>{quality.scoring_rows.toLocaleString("ru-RU")}</strong>
        </div>
        <div>
          <span>С прогнозом</span>
          <strong>{quality.eligible_rows.toLocaleString("ru-RU")}</strong>
        </div>
        <div>
          <span>Без оценки</span>
          <strong>{quality.unavailable_rows.toLocaleString("ru-RU")}</strong>
        </div>
      </div>
      {quality.observations && (
        <>
          <h4>История событий</h4>
          <p>
            {fullDate(quality.observations.start)} —{" "}
            {fullDate(quality.observations.end)} ·{" "}
            {quality.observations.events.toLocaleString("ru-RU")} событий
          </p>
          {quality.observations.missing_days.length > 0 && (
            <p>
              Нет данных за{" "}
              {quality.observations.missing_days.map(fullDate).join(", ")}.
            </p>
          )}
        </>
      )}
      {quality.coverage && (
        <>
          <h4>Каналы по типам оборудования</h4>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Тип оборудования</th>
                  <th>Направление</th>
                  <th>Каналов</th>
                  <th>С прогнозом</th>
                </tr>
              </thead>
              <tbody>
                {quality.coverage.map((row) => (
                  <tr key={row.sensor_type}>
                    <td>{row.sensor_type}</td>
                    <td>{labels[row.direction]}</td>
                    <td>{row.channels}</td>
                    <td>{row.eligible}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
