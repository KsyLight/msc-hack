import { useEffect, useRef, useState } from "react";
import { X, ClipboardPlus, ArrowUpRight } from "lucide-react";
import { Prediction, labels, riskLabels, score, date } from "../api";

export default function PredictionDetail({
  prediction: p,
  close,
  create,
  busy,
}: {
  prediction: Prediction;
  close: () => void;
  create: (comment: string) => Promise<void>;
  busy: boolean;
}) {
  const [comment, setComment] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = dialog.current!;
    el.showModal();
    return () => el.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="detail-dialog"
      onCancel={close}
      onClick={(e) => e.target === dialog.current && close()}
    >
      <div className="detail-head">
        <span className="eyebrow">КАРТОЧКА ПРОГНОЗА</span>
        <button
          className="icon-button"
          aria-label="Закрыть карточку"
          onClick={close}
        >
          <X size={20} />
        </button>
      </div>
      <h2>{p.object_name}</h2>
      <p className="muted">
        {p.entity_id} · {p.sensor_type}
      </p>
      <div className="detail-score">
        <div>
          <span className={`badge ${p.risk}`}>{riskLabels[p.risk]}</span>
          <h3>
            {score(p.score)}
            <small> / 100</small>
          </h3>
        </div>
        <ArrowUpRight size={44} />
      </div>
      <dl>
        {p.sensor_name && (
          <div>
            <dt>Название датчика</dt>
            <dd>{p.sensor_name}</dd>
          </div>
        )}
        {p.system_type && (
          <div>
            <dt>Инженерная система</dt>
            <dd>{p.system_type}</dd>
          </div>
        )}
        {p.system_tag && (
          <div>
            <dt>Тег системы</dt>
            <dd>{p.system_tag}</dd>
          </div>
        )}
        <div>
          <dt>Направление</dt>
          <dd>{labels[p.direction]}</dd>
        </div>
        <div>
          <dt>Прогноз на</dt>
          <dd>
            {date(p.target_start)} — {date(p.target_end)} · +24–48 ч
          </dd>
        </div>
        <div>
          <dt>Известное состояние</dt>
          <dd>{p.state}</dd>
        </div>
      </dl>
      <h4>Наблюдения из истории</h4>
      <div className="factor-list">
        {p.factors.map((f) => (
          <div key={f.feature}>
            <span>{f.label}</span>
            <strong>{f.value}</strong>
          </div>
        ))}
      </div>
      <div className="recommendation">
        <strong>Рекомендация</strong>
        <p>{p.recommendation}</p>
      </div>
      <label className="field-label" htmlFor="ticket-comment">
        Комментарий к заявке
      </label>
      <textarea
        id="ticket-comment"
        value={comment}
        maxLength={2000}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Что нужно проверить на объекте"
        rows={3}
      />
      <button
        className="button primary full"
        disabled={busy || p.score === null}
        onClick={() => void create(comment)}
      >
        <ClipboardPlus size={16} />
        {busy ? "Создаём…" : "Создать заявку на диагностику"}
      </button>
    </dialog>
  );
}
