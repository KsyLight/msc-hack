import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Bell,
  Boxes,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  Database,
  Gauge,
  Layers3,
  LayoutDashboard,
  MapPin,
  Radio,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Wrench,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  Collector,
  Dashboard,
  Direction,
  Model,
  Prediction,
  Quality,
  Ticket,
  date,
  labels,
} from "./api";
import NetworkMap from "./components/NetworkMap";
import PredictionTable from "./components/PredictionTable";
import PredictionDetail from "./components/PredictionDetail";

type Page =
  "overview" | "objects" | "predictions" | "tickets" | "models" | "quality";
const nav = [
  { id: "overview", label: "Обзор системы", icon: LayoutDashboard },
  { id: "objects", label: "Объекты", icon: MapPin },
  { id: "predictions", label: "Журнал прогнозов", icon: Activity },
  { id: "tickets", label: "Заявки на ремонт", icon: ClipboardList },
  { id: "models", label: "Модели", icon: Boxes },
  { id: "quality", label: "Источники данных", icon: Database },
] as const;

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [dashboard, setDashboard] = useState<Dashboard>();
  const [objects, setObjects] = useState<Collector[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [quality, setQuality] = useState<Quality>();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [rows, setRows] = useState<Prediction[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [direction, setDirection] = useState("");
  const [risk, setRisk] = useState("");
  const [objectId, setObjectId] = useState("");
  const [search, setSearch] = useState("");
  const [latest, setLatest] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadingRows, setLoadingRows] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [selected, setSelected] = useState<Prediction>();
  const [revision, setRevision] = useState(0);

  const reload = useCallback(async () => {
    const [d, o, m, q, t] = await Promise.all([
      api<Dashboard>("/dashboard"),
      api<Collector[]>("/objects"),
      api<Model[]>("/models"),
      api<Quality>("/data-quality"),
      api<Ticket[]>("/tickets"),
    ]);
    setDashboard(d);
    setObjects(o);
    setModels(m);
    setQuality(q);
    setTickets(t);
  }, []);
  useEffect(() => {
    void reload().catch((e) => setError(e.message));
  }, [reload]);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoadingRows(true);
      const params = new URLSearchParams({
        limit: "15",
        offset: String(offset),
        latest: String(latest),
        search,
      });
      if (direction) params.set("direction", direction);
      if (risk) params.set("risk", risk);
      if (objectId) params.set("object_id", objectId);
      api<{ items: Prediction[]; total: number }>(`/predictions?${params}`, {
        signal: controller.signal,
      })
        .then((r) => {
          setRows(r.items);
          setTotal(r.total);
        })
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoadingRows(false);
        });
    }, 180);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [direction, risk, objectId, search, offset, latest, revision]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 4500);
    return () => clearTimeout(t);
  }, [toast]);

  const action = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await reload();
      setRevision((v) => v + 1);
      setToast(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const openObject = (id: string) => {
    setObjectId(id);
    setOffset(0);
    setPage("predictions");
  };
  const openDirection = (d: Direction) => {
    setDirection(d);
    setOffset(0);
    setPage("predictions");
  };
  const resetFilters = () => {
    setDirection("");
    setRisk("");
    setObjectId("");
    setSearch("");
    setOffset(0);
    setLatest(true);
  };
  const title = nav.find((n) => n.id === page)?.label ?? "";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          href="#"
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            setPage("overview");
          }}
        >
          <div className="brand-symbol">
            <Layers3 size={25} />
          </div>
          <span>
            контур<span className="brand-dot">.</span>
            <small>ИНЖЕНЕРНАЯ АНАЛИТИКА</small>
          </span>
        </a>
        <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <nav>
          {nav.map((n) => (
            <button
              key={n.id}
              aria-label={n.label}
              className={`nav-item ${page === n.id ? "active" : ""}`}
              onClick={() => setPage(n.id)}
            >
              <n.icon size={18} />
              <span>{n.label}</span>
              {n.id === "tickets" && !!dashboard?.open_tickets && (
                <b>{dashboard.open_tickets}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="system-status">
            <span className="status-dot" />
            <div>
              Локальный контур<small>Горизонт прогноза 24–48 ч</small>
            </div>
          </div>
          <a className="nav-item" href="/docs" target="_blank" rel="noreferrer">
            <CircleHelp size={17} />
            Документация API
            <ArrowUpRight size={13} />
          </a>
          <div className="user">
            <div className="avatar">ОД</div>
            <div>
              Диспетчер ОДС<small>Рабочее место</small>
            </div>
            <ShieldCheck size={16} />
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div className="breadcrumb">
            Мониторинг <ChevronRight size={13} />
            <span>{title}</span>
          </div>
          <div className="topbar-right">
            <span className="local-label">
              <span className="status-dot" /> Локально
            </span>
            <button
              className="icon-button"
              aria-label="Открыть заявки"
              onClick={() => setPage("tickets")}
            >
              <Bell size={18} />
              {!!dashboard?.open_tickets && <i className="notification-dot" />}
            </button>
            <div className="avatar small">ОД</div>
          </div>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">МОНИТОРИНГ ИНЖЕНЕРНЫХ КОЛЛЕКТОРОВ</div>
              <h1>{page === "overview" ? "Всё под контролем" : title}</h1>
              <p>
                {page === "overview"
                  ? "Выявляйте риски заранее. Планируйте обслуживание вовремя."
                  : "История сигналов, прогнозы и действия в одном пространстве."}
              </p>
            </div>
            <button
              className="button"
              disabled={busy}
              onClick={() =>
                void action(
                  () => api("/predictions/run", { method: "POST" }),
                  "Прогнозы пересчитаны по текущему срезу",
                )
              }
            >
              <RefreshCw size={15} className={busy ? "spin" : ""} />
              Обновить прогнозы
            </button>
          </div>
          {error && (
            <div className="error" role="alert">
              {error}
              <button
                onClick={() => {
                  setError("");
                  void reload().catch((e) => setError(e.message));
                }}
              >
                Повторить
              </button>
            </div>
          )}
          {!dashboard ? (
            <div className="loading">
              <div className="loading-dot" />
              <h3>Подключаем систему мониторинга</h3>
              <p>
                Первый запуск включает обучение двух демонстрационных моделей.
              </p>
            </div>
          ) : (
            <>
              <div className="data-banner">
                <div>
                  <Database size={15} />
                  <strong>
                    {dashboard.mode === "demo"
                      ? "Демонстрационный контур"
                      : "Исторический срез"}
                  </strong>
                  <span>
                    {dashboard.mode === "demo"
                      ? "Синтетические данные · показатели не отражают реальные объекты"
                      : "Прогноз по журналам; данные не обновляются в реальном времени"}
                  </span>
                </div>
                <button onClick={() => setPage("quality")}>
                  О данных <ArrowRight size={14} />
                </button>
              </div>
              {page === "overview" && (
                <>
                  <div className="section-caption">
                    <span>Оперативная сводка</span>
                    <span>
                      Срез на {date(dashboard.as_of)}{" "}
                      {new Date(dashboard.as_of).getFullYear()} · 00:00
                    </span>
                  </div>
                  <div className="kpi-grid">
                    {[
                      {
                        label: "Объекты под наблюдением",
                        value: dashboard.objects,
                        sub: "коллекторов в системе",
                        icon: Layers3,
                        color: "green",
                      },
                      {
                        label: "Контролируемые каналы",
                        value: dashboard.channels,
                        sub: `${dashboard.directions.sensor.total} датчиков · ${dashboard.directions.infrastructure.total} оборудования`,
                        icon: Radio,
                        color: "blue",
                      },
                      {
                        label: "Требуют внимания",
                        value: dashboard.high_risk,
                        sub: "каналов с высоким риском",
                        icon: Activity,
                        color: "orange",
                      },
                      {
                        label: "Открытые заявки",
                        value: dashboard.open_tickets,
                        sub: "на превентивную диагностику",
                        icon: ClipboardList,
                        color: "purple",
                      },
                    ].map((k) => (
                      <div className="card kpi" key={k.label}>
                        <div className="kpi-label">
                          {k.label}
                          <span className={`kpi-icon ${k.color}`}>
                            <k.icon size={17} />
                          </span>
                        </div>
                        <div className="kpi-value">
                          {k.value.toLocaleString("ru-RU")}
                        </div>
                        <div className="muted tiny">{k.sub}</div>
                      </div>
                    ))}
                  </div>
                  <div className="overview-grid">
                    <section className="card map-card">
                      <div className="card-heading">
                        <div>
                          <h3>Объекты и риски</h3>
                          <p>Точки внимания на схеме города</p>
                        </div>
                        <button
                          className="text-button"
                          onClick={() => setPage("objects")}
                        >
                          Все объекты <ArrowUpRight size={15} />
                        </button>
                      </div>
                      <NetworkMap objects={objects} onSelect={openObject} />
                      <div className="map-legend">
                        <span>
                          <i className="legend-dot orange" /> Есть высокий риск
                        </span>
                        <span>
                          <i className="legend-dot green" /> Наблюдение
                        </span>
                        <span className="muted">Нажмите на объект</span>
                      </div>
                    </section>
                    <section className="card directions-card">
                      <div className="card-heading">
                        <div>
                          <h3>Направления прогноза</h3>
                          <p>Раннее предупреждение · +24–48 ч</p>
                        </div>
                        <Sparkles size={18} />
                      </div>
                      {(["sensor", "infrastructure"] as Direction[]).map(
                        (d) => (
                          <button
                            className={`direction-card ${d}`}
                            key={d}
                            onClick={() => openDirection(d)}
                          >
                            <div className="direction-title">
                              <span className="direction-icon">
                                {d === "sensor" ? (
                                  <Radio size={20} />
                                ) : (
                                  <Wrench size={20} />
                                )}
                              </span>
                              <span>
                                {labels[d]}
                                <small>
                                  {d === "sensor"
                                    ? "Контактные, объёмные, газовые и другие"
                                    : "Насосы и вентиляционное оборудование"}
                                </small>
                              </span>
                              <ArrowUpRight size={17} />
                            </div>
                            <div className="direction-bottom">
                              <span>
                                <strong>{dashboard.directions[d].high}</strong>{" "}
                                требуют внимания
                              </span>
                              <span>
                                из {dashboard.directions[d].total} каналов
                              </span>
                            </div>
                          </button>
                        ),
                      )}
                      <div className="info-note">
                        <ShieldCheck size={18} />
                        <span>
                          Прогнозируем сигнал «Неисправен». Физический отказ и
                          износ требуют проверки.
                        </span>
                      </div>
                    </section>
                  </div>
                  <section className="card trend-card">
                    <div className="card-heading">
                      <div>
                        <h3>Динамика предупреждений</h3>
                        <p>Количество каналов высокого риска по дням</p>
                      </div>
                      <div className="chart-legend">
                        <span>
                          <i style={{ background: "#39836a" }} />
                          Датчики
                        </span>
                        <span>
                          <i style={{ background: "#94adbf" }} />
                          Инфраструктура
                        </span>
                        <b>{dashboard.trend.length} дней</b>
                      </div>
                    </div>
                    <div className="trend-chart">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart
                          data={dashboard.trend}
                          margin={{ top: 10, right: 10, bottom: 0, left: -25 }}
                        >
                          <defs>
                            <linearGradient
                              id="greenArea"
                              x1="0"
                              x2="0"
                              y1="0"
                              y2="1"
                            >
                              <stop
                                offset="0%"
                                stopColor="#7cae94"
                                stopOpacity={0.23}
                              />
                              <stop
                                offset="100%"
                                stopColor="#7cae94"
                                stopOpacity={0}
                              />
                            </linearGradient>
                          </defs>
                          <CartesianGrid
                            strokeDasharray="3 5"
                            vertical={false}
                            stroke="#e9eeeb"
                          />
                          <XAxis
                            dataKey="date"
                            tickFormatter={date}
                            tick={{ fontSize: 10, fill: "#8a9690" }}
                            axisLine={false}
                            tickLine={false}
                            minTickGap={40}
                          />
                          <YAxis
                            allowDecimals={false}
                            tick={{ fontSize: 10, fill: "#8a9690" }}
                            axisLine={false}
                            tickLine={false}
                          />
                          <Tooltip
                            labelFormatter={(v) => date(String(v))}
                            contentStyle={{
                              borderRadius: 10,
                              border: "1px solid #e5eae6",
                              fontSize: 12,
                            }}
                          />
                          <Area
                            isAnimationActive={false}
                            type="monotone"
                            dataKey="sensor"
                            name="Датчики"
                            stroke="#39836a"
                            strokeWidth={2}
                            fill="url(#greenArea)"
                          />
                          <Area
                            isAnimationActive={false}
                            type="monotone"
                            dataKey="infrastructure"
                            name="Инфраструктура"
                            stroke="#94adbf"
                            strokeWidth={2}
                            fill="transparent"
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </section>
                  <section className="card">
                    <div className="card-heading">
                      <div>
                        <h3>В приоритете</h3>
                        <p>Каналы с наибольшим баллом модели в текущем срезе</p>
                      </div>
                      <button
                        className="text-button"
                        onClick={() => {
                          resetFilters();
                          setPage("predictions");
                        }}
                      >
                        Журнал прогнозов <ArrowRight size={15} />
                      </button>
                    </div>
                    <PredictionTable
                      rows={dashboard.top_predictions}
                      onSelect={setSelected}
                    />
                  </section>
                </>
              )}
              {page === "predictions" && (
                <section className="card">
                  <div className="card-heading">
                    <div>
                      <h3>
                        Журнал прогнозов <span className="count">{total}</span>
                      </h3>
                      <p>
                        Фильтруйте каналы и открывайте карточки для диагностики
                      </p>
                    </div>
                    <a href="/api/predictions/export.csv" className="button">
                      <ArrowDownToLine size={15} />
                      CSV текущего среза
                    </a>
                  </div>
                  <div className="filters">
                    <label className="search">
                      <Search size={16} />
                      <input
                        aria-label="Поиск прогноза"
                        placeholder="Объект, канал, тип…"
                        value={search}
                        onChange={(e) => {
                          setSearch(e.target.value);
                          setOffset(0);
                        }}
                      />
                    </label>
                    <select
                      aria-label="Направление"
                      value={direction}
                      onChange={(e) => {
                        setDirection(e.target.value);
                        setOffset(0);
                      }}
                    >
                      <option value="">Все направления</option>
                      <option value="sensor">Отказ датчика</option>
                      <option value="infrastructure">Инфраструктура</option>
                    </select>
                    <select
                      aria-label="Риск"
                      value={risk}
                      onChange={(e) => {
                        setRisk(e.target.value);
                        setOffset(0);
                      }}
                    >
                      <option value="">Любой риск</option>
                      <option value="high">Высокий</option>
                      <option value="medium">Внимание</option>
                      <option value="low">Низкий</option>
                      <option value="unavailable">Нет оценки</option>
                    </select>
                    <select
                      aria-label="Объект"
                      value={objectId}
                      onChange={(e) => {
                        setObjectId(e.target.value);
                        setOffset(0);
                      }}
                    >
                      <option value="">Все объекты</option>
                      {objects.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.name}
                        </option>
                      ))}
                    </select>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={latest}
                        onChange={(e) => {
                          setLatest(e.target.checked);
                          setOffset(0);
                        }}
                      />
                      Последний срез
                    </label>
                    <button
                      className="icon-button"
                      aria-label="Сбросить фильтры"
                      onClick={resetFilters}
                    >
                      <SlidersHorizontal size={16} />
                    </button>
                  </div>
                  <PredictionTable
                    rows={rows}
                    onSelect={setSelected}
                    loading={loadingRows}
                  />
                  <div className="pagination">
                    <span>
                      {total
                        ? `${offset + 1}–${Math.min(offset + 15, total)} из ${total}`
                        : "0 результатов"}
                    </span>
                    <div>
                      <button
                        className="button"
                        disabled={offset === 0}
                        onClick={() => setOffset(Math.max(0, offset - 15))}
                      >
                        Назад
                      </button>
                      <button
                        className="button"
                        disabled={offset + 15 >= total}
                        onClick={() => setOffset(offset + 15)}
                      >
                        Далее
                      </button>
                    </div>
                  </div>
                </section>
              )}
              {page === "objects" && (
                <>
                  <section className="card">
                    <div className="card-heading">
                      <div>
                        <h3>Схема объектов</h3>
                        <p>{objects.length} объектов в текущем наборе данных</p>
                      </div>
                      <MapPin size={20} />
                    </div>
                    <NetworkMap objects={objects} onSelect={openObject} />
                  </section>
                  <div className="objects-grid">
                    {objects.map((o) => (
                      <button
                        key={o.id}
                        className="card object-card"
                        onClick={() => openObject(o.id)}
                      >
                        <span className="object-card-top">
                          <span className="object-icon">
                            <Layers3 size={20} />
                          </span>
                          <ArrowUpRight size={17} />
                        </span>
                        <h3>{o.name}</h3>
                        <p>
                          {o.district} · {o.id}
                        </p>
                        <div>
                          <span>{o.channels} каналов</span>
                          <span className={o.high_risk ? "warning-text" : ""}>
                            {o.high_risk} требуют внимания
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </>
              )}
              {page === "tickets" && (
                <section className="card">
                  <div className="card-heading">
                    <div>
                      <h3>Превентивное обслуживание</h3>
                      <p>
                        Заявки сохраняются локально и доступны после перезапуска
                      </p>
                    </div>
                    <button
                      className="button primary"
                      disabled={busy}
                      onClick={() =>
                        void action(
                          () => api("/tickets/generate", { method: "POST" }),
                          "Заявки по высокому риску сформированы",
                        )
                      }
                    >
                      <Sparkles size={15} />
                      Сформировать по рискам
                    </button>
                  </div>
                  {tickets.length ? (
                    <div className="ticket-list">
                      {tickets.map((t) => (
                        <div className="ticket" key={t.id}>
                          <div className="ticket-number">
                            #{String(t.id).padStart(4, "0")}
                          </div>
                          <div className="ticket-description">
                            <button
                              className="object-link"
                              onClick={() => setSelected(t.prediction)}
                            >
                              {t.prediction.object_name} ·{" "}
                              {t.prediction.entity_id}
                            </button>
                            <p>
                              {t.comment || "Диагностика по прогнозу риска"}
                            </p>
                            <small>
                              {date(t.created_at)} ·{" "}
                              {t.automatic
                                ? "Сформирована автоматически"
                                : "Создана диспетчером"}
                            </small>
                          </div>
                          <span
                            className={`badge ${t.status === "done" ? "low" : "medium"}`}
                          >
                            {
                              (
                                {
                                  new: "Новая",
                                  in_progress: "В работе",
                                  done: "Завершена",
                                  dismissed: "Отклонена",
                                } as Record<string, string>
                              )[t.status]
                            }
                          </span>
                          {["new", "in_progress"].includes(t.status) && (
                            <div className="ticket-actions">
                              <button
                                className="button"
                                disabled={busy}
                                onClick={() =>
                                  void action(
                                    () =>
                                      api(`/tickets/${t.id}`, {
                                        method: "PATCH",
                                        body: JSON.stringify({
                                          status:
                                            t.status === "new"
                                              ? "in_progress"
                                              : "done",
                                          comment: t.comment,
                                        }),
                                      }),
                                    "Статус заявки обновлён",
                                  )
                                }
                              >
                                {t.status === "new"
                                  ? "Взять в работу"
                                  : "Завершить"}
                              </button>
                              <button
                                className="text-button"
                                disabled={busy}
                                onClick={() =>
                                  void action(
                                    () =>
                                      api(`/tickets/${t.id}`, {
                                        method: "PATCH",
                                        body: JSON.stringify({
                                          status: "dismissed",
                                          comment: t.comment,
                                        }),
                                      }),
                                    "Заявка отклонена",
                                  )
                                }
                              >
                                Отклонить
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="empty">
                      <ClipboardList size={34} />
                      <h3>Заявок пока нет</h3>
                      <p>
                        Создайте заявку из карточки прогноза или сформируйте по
                        высокому риску.
                      </p>
                    </div>
                  )}
                </section>
              )}
              {page === "models" && (
                <>
                  <div className="model-grid">
                    {models.map((m) => (
                      <section className="card model-card" key={m.direction}>
                        <div className="model-title">
                          <span className="object-icon">
                            <Boxes size={21} />
                          </span>
                          <span className="badge low">Модель загружена</span>
                        </div>
                        <h2>{labels[m.direction]}</h2>
                        <p>
                          {m.algorithm} · версия {m.version}
                        </p>
                        <div className="model-metrics">
                          {[
                            ["Precision", m.test.precision],
                            ["Recall", m.test.recall],
                            ["PR-AUC", m.test.pr_auc],
                          ].map(([l, v]) => (
                            <div key={String(l)}>
                              <span>{l}</span>
                              <strong>{Number(v).toFixed(3)}</strong>
                            </div>
                          ))}
                        </div>
                        <div className="note">
                          {m.provenance === "synthetic_demo"
                            ? "Метрики на синтетическом тесте. Не подтверждают качество на данных кейса."
                            : m.meets_case_metrics
                              ? "Целевые Precision и Recall достигнуты для proxy-метки на временном тесте."
                              : "Целевые Precision > 0.7 и Recall > 0.5 пока не достигнуты одновременно."}
                        </div>
                        <dl>
                          <div>
                            <dt>Тестовых строк</dt>
                            <dd>{m.test.rows.toLocaleString("ru-RU")}</dd>
                          </div>
                          <div>
                            <dt>Положительных меток</dt>
                            <dd>{m.test.positives}</dd>
                          </div>
                          <div>
                            <dt>Ложных предупреждений</dt>
                            <dd>{m.test.false_positives}</dd>
                          </div>
                          <div>
                            <dt>Признаки / обучение</dt>
                            <dd>
                              {m.features.length} /{" "}
                              {m.training_seconds.toFixed(1)} с
                            </dd>
                          </div>
                        </dl>
                        <details>
                          <summary>Контракт признаков</summary>
                          <div className="feature-tags">
                            {m.features.map((f) => (
                              <code key={f}>{f}</code>
                            ))}
                          </div>
                        </details>
                        <h4>Сравнение на validation</h4>
                        <div className="candidate-list">
                          {m.validation_candidates.map((c) => (
                            <div key={c.algorithm}>
                              <span>{c.algorithm}</span>
                              <strong>AP {c.pr_auc.toFixed(3)}</strong>
                            </div>
                          ))}
                        </div>
                      </section>
                    ))}
                  </div>
                  <div className="info-note">
                    <Gauge size={20} />
                    <span>
                      Порог выбирается на validation. Временные выборки
                      разделены зазором 48 часов. Тест используется после выбора
                      модели.
                    </span>
                  </div>
                </>
              )}
              {page === "quality" && quality && (
                <>
                  <section className="card quality-card">
                    <div className="card-heading">
                      <div>
                        <h3>Прозрачность данных</h3>
                        <p>{quality.notice}</p>
                      </div>
                      <Database size={24} />
                    </div>
                    <div className="quality-stats">
                      <div>
                        <span>Режим</span>
                        <strong>
                          {quality.mode === "demo"
                            ? "Демонстрация"
                            : "Данные ноутбука"}
                        </strong>
                      </div>
                      <div>
                        <span>Строк для расчёта</span>
                        <strong>
                          {quality.scoring_rows.toLocaleString("ru-RU")}
                        </strong>
                      </div>
                      <div>
                        <span>Допущено к прогнозу</span>
                        <strong>
                          {quality.eligible_rows.toLocaleString("ru-RU")}
                        </strong>
                      </div>
                      <div>
                        <span>Без оценки</span>
                        <strong>{quality.unavailable_rows}</strong>
                      </div>
                    </div>
                    <h4>Что означает прогноз</h4>
                    <p>
                      Модель использует только прошлую историю сообщений. Цель —
                      новый эпизод «Неисправен» в интервале от 24 до 48 часов
                      после момента прогноза. Каналы с уже известной
                      неисправностью или недостаточной историей не получают
                      оценку раннего предупреждения.
                    </p>
                    <div className="limitations">
                      {quality.limitations.map((l) => (
                        <div key={l}>
                          <CircleHelp size={17} />
                          <span>{l}</span>
                        </div>
                      ))}
                    </div>
                  </section>
                  <section className="card quality-card">
                    <h3>Почему выбраны эти направления</h3>
                    <p>
                      Ноутбук содержит разметку неисправности для датчиков,
                      насосов и вентиляторов. Для пожарного риска нет
                      проверенной разметки пожаров и связанных графиков горячих
                      работ. Для оценки физического износа нужны акты
                      обследований, возраст и факты ремонтов. Текущая модель
                      инфраструктуры помогает приоритизировать диагностику
                      насосов и вентиляторов по сигналам.
                    </p>
                  </section>
                </>
              )}
            </>
          )}
          <footer>
            <span>
              <Layers3 size={13} /> Контур · Предиктивная аналитика
            </span>
            <span>ЛЦТ 2026 / Кейс 08</span>
          </footer>
        </div>
      </main>
      {selected && (
        <PredictionDetail
          prediction={selected}
          close={() => setSelected(undefined)}
          busy={busy}
          create={async (comment) => {
            await action(async () => {
              await api("/tickets", {
                method: "POST",
                body: JSON.stringify({ prediction_id: selected.id, comment }),
              });
              setSelected(undefined);
            }, "Заявка на диагностику создана");
          }}
        />
      )}
      {toast && (
        <div className="toast" role="status">
          <Check size={17} />
          {toast}
        </div>
      )}
    </div>
  );
}
