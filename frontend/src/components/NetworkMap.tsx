import { useState } from "react";
import { MapPin, Minus, Plus, ChevronRight } from "lucide-react";
import { Collector } from "../api";

export default function NetworkMap({
  objects,
  onSelect,
}: {
  objects: Collector[];
  onSelect: (id: string) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const located = objects.filter(
    (o) => o.latitude !== null && o.longitude !== null,
  );
  return (
    <div className="network-map">
      {located.length ? (
        <>
          <svg
            viewBox="0 0 700 350"
            role="img"
            aria-label="Схема расположения демонстрационных объектов"
          >
            <defs>
              <pattern
                id="mapgrid"
                width="24"
                height="24"
                patternUnits="userSpaceOnUse"
              >
                <path
                  d="M24 0H0V24"
                  fill="none"
                  stroke="#d8e3da"
                  strokeWidth=".5"
                />
              </pattern>
            </defs>
            <rect width="700" height="350" fill="#eaf0e9" />
            <rect width="700" height="350" fill="url(#mapgrid)" />
            <g
              transform={`translate(350 175) scale(${zoom}) translate(-350 -175)`}
            >
              <path
                d="M0 74L120 48 183 126 246 134 290 213 420 196 490 244 553 224 590 298 710 320"
                fill="none"
                stroke="#d2e0dc"
                strokeWidth="28"
              />
              <g fill="none" stroke="#f6faf7" strokeWidth="12">
                <ellipse cx="342" cy="158" rx="211" ry="128" />
                <ellipse cx="348" cy="166" rx="121" ry="85" />
                <path d="M35 27L630 306M100 340L550 8M20 188L700 108M311 0L391 350" />
              </g>
              <g fill="none" stroke="#d8e3da" strokeWidth="1.5">
                <ellipse cx="342" cy="158" rx="211" ry="128" />
                <ellipse cx="348" cy="166" rx="121" ry="85" />
                <path d="M35 27L630 306M100 340L550 8M20 188L700 108M311 0L391 350" />
              </g>
              <path
                d="M56 265L181 204 265 222 346 165 412 190 518 128 621 152"
                fill="none"
                stroke="#7d8465"
                strokeWidth="2"
                strokeDasharray="5 5"
              />
              <text
                x="309"
                y="182"
                fill="#3b3f2f"
                fontSize="12"
                letterSpacing="2"
              >
                МОСКВА
              </text>
              {located.map((o) => {
                const x = 85 + ((o.longitude! - 37.49) / 0.24) * 530;
                const y = 292 - ((o.latitude! - 55.69) / 0.12) * 245;
                return (
                  <g
                    key={o.id}
                    className="map-marker"
                    role="button"
                    tabIndex={0}
                    aria-label={`Объект ${o.name}, высокий риск: ${o.high_risk}`}
                    onClick={() => onSelect(o.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelect(o.id);
                      }
                    }}
                  >
                    <circle
                      cx={x}
                      cy={y}
                      r="15"
                      fill={o.high_risk ? "#c2847740" : "#7d846540"}
                    />
                    <circle
                      cx={x}
                      cy={y}
                      r="7"
                      fill={o.high_risk ? "#c28477" : "#687E55"}
                      stroke="white"
                      strokeWidth="2.5"
                    />
                    <title>
                      {o.name}: {o.high_risk} каналов высокого риска
                    </title>
                    <text x={x + 12} y={y - 11} fontSize="12" fill="#3b3f2f">
                      {o.name}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>
          <div className="map-caption">
            <MapPin size={12} /> Условная схема · демокоординаты
          </div>
          <div className="map-zoom">
            <button
              aria-label="Увеличить карту"
              onClick={() => setZoom(Math.min(zoom + 0.2, 1.8))}
            >
              <Plus size={16} />
            </button>
            <button
              aria-label="Уменьшить карту"
              onClick={() => setZoom(Math.max(zoom - 0.2, 0.8))}
            >
              <Minus size={16} />
            </button>
          </div>
        </>
      ) : (
        <div className="object-ranking">
          {[...objects]
            .sort(
              (a, b) =>
                b.high_risk - a.high_risk ||
                (b.max_score ?? -1) - (a.max_score ?? -1),
            )
            .slice(0, 5)
            .map((object) => (
              <button key={object.id} onClick={() => onSelect(object.id)}>
                <MapPin size={17} />
                <span>
                  <strong>{object.name}</strong>
                  <small>{object.channels} каналов под наблюдением</small>
                </span>
                <b className={`badge ${object.high_risk ? "high" : "low"}`}>
                  {object.high_risk} высокого риска
                </b>
                <ChevronRight size={15} />
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
