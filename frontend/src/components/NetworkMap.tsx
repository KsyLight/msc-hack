import { useState } from "react";
import { MapPin, Minus, Plus } from "lucide-react";
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
                  stroke="#dce6df"
                  strokeWidth=".5"
                />
              </pattern>
            </defs>
            <rect width="700" height="350" fill="#edf2eb" />
            <rect width="700" height="350" fill="url(#mapgrid)" />
            <g
              transform={`translate(350 175) scale(${zoom}) translate(-350 -175)`}
            >
              <path
                d="M0 74L120 48 183 126 246 134 290 213 420 196 490 244 553 224 590 298 710 320"
                fill="none"
                stroke="#c3dce0"
                strokeWidth="28"
              />
              <g fill="none" stroke="#fffdf5" strokeWidth="12">
                <ellipse cx="342" cy="158" rx="211" ry="128" />
                <ellipse cx="348" cy="166" rx="121" ry="85" />
                <path d="M35 27L630 306M100 340L550 8M20 188L700 108M311 0L391 350" />
              </g>
              <g fill="none" stroke="#ced8cd" strokeWidth="1.5">
                <ellipse cx="342" cy="158" rx="211" ry="128" />
                <ellipse cx="348" cy="166" rx="121" ry="85" />
                <path d="M35 27L630 306M100 340L550 8M20 188L700 108M311 0L391 350" />
              </g>
              <path
                d="M56 265L181 204 265 222 346 165 412 190 518 128 621 152"
                fill="none"
                stroke="#83a697"
                strokeWidth="2"
                strokeDasharray="5 5"
              />
              <text
                x="309"
                y="182"
                fill="#8f9b91"
                fontSize="11"
                letterSpacing="3"
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
                    onKeyDown={(e) => e.key === "Enter" && onSelect(o.id)}
                  >
                    <circle
                      cx={x}
                      cy={y}
                      r="15"
                      fill={o.high_risk ? "#e8907740" : "#6a998240"}
                    />
                    <circle
                      cx={x}
                      cy={y}
                      r="7"
                      fill={o.high_risk ? "#d96c4f" : "#47856a"}
                      stroke="white"
                      strokeWidth="2.5"
                    />
                    <title>
                      {o.name}: {o.high_risk} каналов высокого риска
                    </title>
                    <text x={x + 12} y={y - 11} fontSize="10" fill="#596a61">
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
        <div className="map-empty">
          <MapPin size={28} />
          <strong>Координаты не предоставлены</strong>
          <span>
            Объекты доступны в реестре ниже.
            <br />
            Для карты нужен справочник координат.
          </span>
        </div>
      )}
    </div>
  );
}
