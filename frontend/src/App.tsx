import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Bell,
  Check,
  ChevronRight,
  ClipboardList,
  Database,
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
  Prediction,
  Quality,
  Ticket,
  date,
  labels,
} from "./api";
import NetworkMap from "./components/NetworkMap";
import PredictionTable from "./components/PredictionTable";
import PredictionDetail from "./components/PredictionDetail";
import DataStatus from "./components/DataStatus";

type Page = "overview" | "objects" | "predictions" | "tickets" | "quality";
const nav = [
  { id: "overview", label: "Обзор системы", icon: LayoutDashboard },
  { id: "objects", label: "Объекты", icon: MapPin },
  { id: "predictions", label: "Журнал прогнозов", icon: Activity },
  { id: "tickets", label: "Заявки на ремонт", icon: ClipboardList },
  { id: "quality", label: "Состояние данных", icon: Database },
] as const;

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [reducedMotion, setReducedMotion] = useState(false);
  const [dashboard, setDashboard] = useState<Dashboard>();
  const [objects, setObjects] = useState<Collector[]>([]);
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
  const [historyDays, setHistoryDays] = useState(30);
  const hasObservations = Boolean(dashboard?.observations?.length);
  const chartData =
    (hasObservations ? dashboard?.observations : dashboard?.trend)?.slice(
      -historyDays,
    ) ?? [];

  const reload = useCallback(async () => {
    const [d, o, q, t] = await Promise.all([
      api<Dashboard>("/dashboard"),
      api<Collector[]>("/objects"),
      api<Quality>("/data-quality"),
      api<Ticket[]>("/tickets"),
    ]);
    setDashboard(d);
    setObjects(o);
    setQuality(q);
    setTickets(t);
  }, []);
  useEffect(() => {
    void reload().catch((e) => setError(e.message));
  }, [reload]);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updatePreference = () => setReducedMotion(preference.matches);
    updatePreference();
    preference.addEventListener("change", updatePreference);
    return () => preference.removeEventListener("change", updatePreference);
  }, []);
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
              aria-current={page === n.id ? "page" : undefined}
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
              Мониторинг коллекторов<small>Окно прогноза указано в карточке</small>
            </div>
          </div>
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
              {dashboard && <>Данные на {new Date(dashboard.as_of).toLocaleDateString("ru-RU")}</>}
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
          <div className={`page-heading ${page === "overview" ? "overview-heading" : ""}`}>
            <div>
              <div className="eyebrow">МОНИТОРИНГ ИНЖЕНЕРНЫХ КОЛЛЕКТОРОВ</div>
              <h1>
                {page === "overview"
                  ? dashboard?.mode === "real"
                    ? "Мониторинг коллекторов"
                    : "Аналитическая система"
                  : title}
              </h1>
              <p>
                {page === "overview"
                  ? "Следите за состоянием коллекторов в реальном времени, получайте предупреждения о рисках и планируйте обслуживание заранее."
                  : "История сигналов, прогнозы и действия в одном пространстве."}
              </p>
            </div>
            <button
              className="button"
              disabled={busy}
              onClick={() =>
                void action(
                  () => api("/predictions/run", { method: "POST" }),
                  "Прогнозы обновлены",
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
              <p>Загружаем прогнозы и события.</p>
            </div>
          ) : (
            <>
              {dashboard.mode === "demo" && <div className="data-banner">
                <div>
                  <Database size={15} />
                  <strong>Демонстрационный режим</strong>
                </div>
              </div>}
              {page === "overview" && (
                <>
                  <div className="section-caption">
                    <span>Оперативная сводка</span>
                    <span>
                      Данные на {date(dashboard.as_of)}{" "}
                      {new Date(dashboard.as_of).getFullYear()} ·{" "}
                      {new Date(dashboard.as_of).toLocaleTimeString("ru-RU", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                  <div className="kpi-grid">
                    {[
                      {
                        label: "Объекты под наблюдением",
                        value: dashboard.objects,
                        sub: "объектов под наблюдением",
                        icon: Layers3,
                        color: "green",
                      },
                      {
                        label: "Контролируемые каналы",
                        value: dashboard.channels,
                        sub: `${dashboard.directions.sensor?.total ?? 0} датчиков · ${dashboard.directions.infrastructure?.total ?? 0} оборудования${dashboard.directions.smoke ? ` · ${dashboard.directions.smoke.total} дым` : ""}`,
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
                          <p>
                            {objects.some((object) => object.latitude !== null)
                              ? "Точки внимания на схеме города"
                              : "Приоритет диагностики"}
                          </p>
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
                          <p>Прогноз зарегистрированной неисправности</p>
                        </div>
                        <Sparkles size={18} />
                      </div>
                      {(
                        Object.keys(dashboard.directions) as Direction[]
                      ).map((d) => (
                          <button
                            className={`direction-card ${d}`}
                            key={d}
                            onClick={() => openDirection(d)}
                          >
                            <div className="direction-title">
                              <span className="direction-icon">
                                {d === "sensor" ? (
                                  <Radio size={20} />
                                ) : d === "smoke" ? (
                                  <Bell size={20} />
                                ) : (
                                  <Wrench size={20} />
                                )}
                              </span>
                              <span>
                                {labels[d]}
                                <small>
                                  {d === "sensor"
                                    ? "Контактные, объёмные, газовые и другие"
                                    : d === "smoke"
                                      ? "Зарегистрированный сигнал дыма, не пожар"
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
                        ))}
                    </section>
                  </div>
                  <section className="card trend-card">
                    <div className="card-heading">
                      <div>
                        <h3>
                          {hasObservations
                            ? "История сообщений о неисправности"
                            : "Динамика предупреждений"}
                        </h3>
                        <p>
                          {hasObservations
                            ? "Сообщения датчиков и оборудования по дням"
                            : "Количество каналов высокого риска по дням"}
                        </p>
                      </div>
                      <div className="chart-legend">
                        <span>
                          <i style={{ background: "#7d8465" }} />
                          Датчики
                        </span>
                        <span>
                          <i style={{ background: "#c28477" }} />
                          Инфраструктура
                        </span>
                        {hasObservations ? (
                          <select
                            aria-label="Период истории"
                            value={historyDays}
                            onChange={(event) =>
                              setHistoryDays(Number(event.target.value))
                            }
                          >
                            <option value={30}>30 дней</option>
                            <option value={90}>90 дней</option>
                            <option value={366}>Весь период</option>
                          </select>
                        ) : (
                          <b>{dashboard.trend.length} дней</b>
                        )}
                      </div>
                    </div>
                    <div className="trend-chart">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart
                          data={chartData}
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
                                stopColor="#7d8465"
                                stopOpacity={0.23}
                              />
                              <stop
                                offset="100%"
                                stopColor="#7d8465"
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
                            tick={{ fontSize: 12, fill: "#3b3f2f" }}
                            axisLine={false}
                            tickLine={false}
                            minTickGap={40}
                          />
                          <YAxis
                            allowDecimals={false}
                            tick={{ fontSize: 12, fill: "#3b3f2f" }}
                            axisLine={false}
                            tickLine={false}
                          />
                          <Tooltip
                            labelFormatter={(v) => date(String(v))}
                            contentStyle={{
                              borderRadius: 10,
                              border: "1px solid #e5eae6",
                              fontSize: 14,
                            }}
                          />
                          <Area
                            isAnimationActive={!reducedMotion}
                            animationDuration={650}
                            animationEasing="ease-in-out"
                            type="monotone"
                            dataKey="sensor"
                            name="Датчики"
                            stroke="#7d8465"
                            strokeWidth={2}
                            fill="url(#greenArea)"
                          />
                          <Area
                            isAnimationActive={!reducedMotion}
                            animationDuration={650}
                            animationEasing="ease-in-out"
                            type="monotone"
                            dataKey="infrastructure"
                            name="Инфраструктура"
                            stroke="#c28477"
                            strokeWidth={2}
                            fill="transparent"
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                    {hasObservations && (
                      <p className="muted tiny chart-note">
                        {chartData.length > 0 && <>{new Date(chartData[0].date).toLocaleDateString("ru-RU")} — {new Date(chartData[chartData.length - 1].date).toLocaleDateString("ru-RU")}</>}
                      </p>
                    )}
                  </section>
                  <section className="card">
                    <div className="card-heading">
                      <div>
                        <h3>В приоритете</h3>
                        <p>Каналы с наибольшей оценкой риска</p>
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
                      Скачать CSV
                    </a>
                  </div>
                  <div className="filters">
                    <label className="search">
                      <Search size={16} />
                      <input
                        aria-label="Поиск прогноза"
                        placeholder="Объект, канал, тип, система…"
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
                      <option value="smoke">Сигнал дыма</option>
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
                      Последние прогнозы
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
                        <p>{objects.length} объектов под наблюдением</p>
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
              {page === "quality" && quality && (
                <DataStatus quality={quality} />
              )}
            </>
          )}
          <footer>
            <span>
              <Layers3 size={13} /> Контур · Предиктивная аналитика
            </span>
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
