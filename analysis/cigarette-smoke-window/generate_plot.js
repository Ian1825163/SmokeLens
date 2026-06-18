const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "../..");
const INPUT_CSV = path.join(ROOT, "data", "smokelens.csv");
const OUTPUT_DIR = __dirname;
const WINDOW_START = 1781505280;
const WINDOW_END = 1781505430;

const LABEL_LEVELS = {
  normal_air: 0,
  cigarette_smoke: 1
};

const LABEL_COLORS = {
  normal_air: "#2f7d57",
  cigarette_smoke: "#c43d35"
};

const DASHBOARD_SERIES = [
  { key: "vocRaw", csv: "voc_raw", label: "VOC raw", color: "#2563eb" },
  { key: "coRaw", csv: "co_raw", label: "CO raw", color: "#7c3aed" },
  { key: "pm1_0", csv: "pm1_0", label: "PM1.0", color: "#0f766e" },
  { key: "pm2_5", csv: "pm2_5", label: "PM2.5", color: "#c43d35" },
  { key: "pm10", csv: "pm10", label: "PM10", color: "#d97706" },
  { key: "temperature", csv: "temperature", label: "Temp C", color: "#dc2626" },
  { key: "humidity", csv: "humidity", label: "RH %", color: "#0891b2" }
];

function splitCsvLineEnough(line) {
  return line.split(",");
}

function parseRows() {
  const lines = fs.readFileSync(INPUT_CSV, "utf8").split(/\r?\n/);
  const rows = [];

  for (let index = 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line) continue;
    const parts = splitCsvLineEnough(line);
    const timestamp = Number(parts[2]);
    const mode = parts[3];
    if (
      mode !== "inference" ||
      timestamp < WINDOW_START ||
      timestamp > WINDOW_END
    ) {
      continue;
    }

    const modelIndex = parts.findIndex((part) =>
      part === "rule_fallback_v0" || part.startsWith("smokelens_")
    );
    if (modelIndex < 0) {
      continue;
    }

    rows.push({
      timestamp,
      seconds: timestamp - WINDOW_START,
      label: parts[6],
      cigaretteDetected: parts[modelIndex - 2] === "true",
      score: Number(parts[modelIndex - 1]),
      vocRaw: Number(parts[modelIndex + 1]),
      coRaw: Number(parts[modelIndex + 2]),
      vocMv: Number(parts[modelIndex + 3]),
      coMv: Number(parts[modelIndex + 4]),
      pm1_0: Number(parts[modelIndex + 5]),
      pm2_5: Number(parts[modelIndex + 6]),
      pm10: Number(parts[modelIndex + 7]),
      temperature: Number(parts[modelIndex + 8]),
      humidity: Number(parts[modelIndex + 9]),
      createdAt: parts.at(-1)
    });
  }

  return rows;
}

function minMax(rows, key) {
  return rows.reduce(
    (range, row) => ({
      min: Math.min(range.min, row[key]),
      max: Math.max(range.max, row[key])
    }),
    { min: Infinity, max: -Infinity }
  );
}

function scale(domainMin, domainMax, rangeMin, rangeMax) {
  return (value) => {
    if (domainMax === domainMin) return (rangeMin + rangeMax) / 2;
    const t = (value - domainMin) / (domainMax - domainMin);
    return rangeMin + t * (rangeMax - rangeMin);
  };
}

function linePath(rows, x, y, key) {
  return rows
    .map((row, index) => `${index === 0 ? "M" : "L"}${x(row.seconds).toFixed(2)},${y(row[key]).toFixed(2)}`)
    .join(" ");
}

function labelRuns(rows) {
  const runs = [];
  for (const row of rows) {
    const last = runs.at(-1);
    if (last && last.label === row.label && row.timestamp <= last.endTimestamp + 2) {
      last.endTimestamp = row.timestamp;
      last.endSeconds = row.seconds;
      last.count += 1;
    } else {
      runs.push({
        label: row.label,
        startTimestamp: row.timestamp,
        endTimestamp: row.timestamp,
        startSeconds: row.seconds,
        endSeconds: row.seconds,
        count: 1
      });
    }
  }
  return runs;
}

function writeWindowCsv(rows) {
  const header = [
    "timestamp",
    "seconds_from_start",
    "created_at",
    "inference_class",
    "cigarette_detected",
    "inference_score",
    "voc_raw",
    "co_raw",
    "pm1_0",
    "pm2_5",
    "pm10",
    "temperature",
    "humidity"
  ];
  const body = rows.map((row) =>
    [
      row.timestamp,
      row.seconds,
      row.createdAt,
      row.label,
      row.cigaretteDetected,
      row.score,
      row.vocRaw,
      row.coRaw,
      row.pm1_0,
      row.pm2_5,
      row.pm10,
      row.temperature,
      row.humidity
    ].join(",")
  );
  fs.writeFileSync(path.join(OUTPUT_DIR, "window.csv"), `${header.join(",")}\n${body.join("\n")}\n`);
}

function buildSvg(rows) {
  const width = 1280;
  const height = 790;
  const margin = { top: 78, right: 70, bottom: 70, left: 82 };
  const labelTop = 108;
  const labelHeight = 68;
  const seriesTop = 232;
  const seriesHeight = 48;
  const seriesGap = 18;
  const seriesBottom =
    seriesTop + DASHBOARD_SERIES.length * seriesHeight + (DASHBOARD_SERIES.length - 1) * seriesGap;
  const plotWidth = width - margin.left - margin.right;
  const x = scale(0, WINDOW_END - WINDOW_START, margin.left, width - margin.right);
  const labelY = (label) => labelTop + (LABEL_LEVELS[label] === 1 ? 18 : 52);
  const runs = labelRuns(rows);
  const smokeRun = runs.find((run) => run.label === "cigarette_smoke");

  const labelSegments = runs
    .map((run) => {
      const x1 = x(run.startSeconds);
      const x2 = x(run.endSeconds + 1);
      const y = labelY(run.label);
      return `<line x1="${x1.toFixed(2)}" y1="${y}" x2="${x2.toFixed(2)}" y2="${y}" stroke="${LABEL_COLORS[run.label]}" stroke-width="7" stroke-linecap="round"/>`;
    })
    .join("\n    ");

  const transitionLines = runs
    .slice(1)
    .map((run) => {
      const xPos = x(run.startSeconds);
      return `<line x1="${xPos.toFixed(2)}" y1="${labelTop}" x2="${xPos.toFixed(2)}" y2="${seriesBottom}" stroke="#8a8f98" stroke-width="1.5" stroke-dasharray="5 8"/>`;
    })
    .join("\n    ");

  const smokeBand = runs
    .filter((run) => run.label === "cigarette_smoke")
    .map((run) => {
      const x1 = x(run.startSeconds);
      const w = x(run.endSeconds + 1) - x1;
      return `<rect x="${x1.toFixed(2)}" y="${labelTop - 14}" width="${w.toFixed(2)}" height="${seriesBottom - labelTop + 14}" fill="#c43d35" opacity="0.08"/>`;
    })
    .join("\n    ");

  const ticks = [
    { second: 0, label: "14:34:40" },
    { second: 20, label: "14:35:00" },
    { second: 50, label: "14:35:30" },
    { second: 80, label: "14:36:00" },
    { second: 110, label: "14:36:30" },
    { second: 140, label: "14:37:00" }
  ]
    .map(({ second, label }) => {
      const xPos = x(second);
      return `<line x1="${xPos.toFixed(2)}" y1="${seriesBottom}" x2="${xPos.toFixed(2)}" y2="${seriesBottom + 8}" stroke="#68707c"/>
      <text x="${xPos.toFixed(2)}" y="${seriesBottom + 30}" text-anchor="middle" font-size="15" fill="#374151">${label}</text>`;
    })
    .join("\n    ");

  const labelText = runs
    .map((run) => {
      const center = (x(run.startSeconds) + x(run.endSeconds + 1)) / 2;
      const y = labelY(run.label) - 10;
      const text = run.label === "cigarette_smoke" ? "cigarette_smoke" : "normal_air";
      return `<text x="${center.toFixed(2)}" y="${y}" text-anchor="middle" font-size="12" font-weight="700" fill="${LABEL_COLORS[run.label]}">${text}</text>`;
    })
    .join("\n    ");

  const smokeBoundaryMarkers = smokeRun
    ? [
        {
          seconds: smokeRun.startSeconds,
          text: "14:35:24",
          anchor: "middle",
          dx: 0
        },
        {
          seconds: smokeRun.endSeconds + 1,
          text: "14:36:29",
          anchor: "middle",
          dx: 0
        }
      ]
        .map((marker) => {
          const xPos = x(marker.seconds);
          return `<g>
    <line x1="${xPos.toFixed(2)}" y1="${seriesBottom + 54}" x2="${xPos.toFixed(2)}" y2="${seriesBottom + 36}" stroke="#9f302a" stroke-width="2"/>
    <path d="M${(xPos - 6).toFixed(2)},${(seriesBottom + 44).toFixed(2)} L${xPos.toFixed(2)},${(seriesBottom + 54).toFixed(2)} L${(xPos + 6).toFixed(2)},${(seriesBottom + 44).toFixed(2)}" fill="none" stroke="#9f302a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="${(xPos + marker.dx).toFixed(2)}" y="${seriesBottom + 78}" text-anchor="${marker.anchor}" font-size="14" font-weight="700" fill="#9f302a">${marker.text}</text>
  </g>`;
        })
        .join("\n  ")
    : "";

  const seriesPanels = DASHBOARD_SERIES.map((series, index) => {
    const top = seriesTop + index * (seriesHeight + seriesGap);
    const range = minMax(rows, series.key);
    const pad = Math.max((range.max - range.min) * 0.12, 0.8);
    const y = scale(range.min - pad, range.max + pad, top + seriesHeight, top);
    const mid = (range.min + range.max) / 2;
    return `<g>
    <rect x="${margin.left}" y="${top - 8}" width="${plotWidth}" height="${seriesHeight + 16}" fill="#ffffff" stroke="#d9dee7"/>
    <line x1="${margin.left}" y1="${y(mid).toFixed(2)}" x2="${width - margin.right}" y2="${y(mid).toFixed(2)}" stroke="#eef2f7"/>
    <path d="${linePath(rows, x, y, series.key)}" fill="none" stroke="${series.color}" stroke-width="2.5"/>
    <text x="${margin.left - 12}" y="${top + 18}" text-anchor="end" font-size="15" font-weight="700" fill="${series.color}">${series.label}</text>
    <text x="${width - margin.right + 8}" y="${top + 6}" font-size="12" fill="#4b5563">${range.max.toFixed(1)}</text>
    <text x="${width - margin.right + 8}" y="${top + seriesHeight}" font-size="12" fill="#4b5563">${range.min.toFixed(1)}</text>
  </g>`;
  }).join("\n  ");

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="100%" height="100%" fill="#f8fafc"/>
  <text x="${margin.left}" y="42" font-size="28" font-weight="800" fill="#111827">SmokeLens dashboard values during label transition</text>
  <text x="${margin.left}" y="68" font-size="16" fill="#4b5563">2026-06-15 14:34:40-14:37:10 UTC+8 · timestamp ${WINDOW_START}-${WINDOW_END}</text>
  <g transform="translate(858,34)">
    <rect x="0" y="-8" width="18" height="16" fill="#c43d35" opacity="0.12"/><text x="26" y="5" font-size="14" fill="#374151">cigarette_smoke interval</text>
    <line x1="0" y1="28" x2="30" y2="28" stroke="#8a8f98" stroke-width="1.5" stroke-dasharray="5 8"/><text x="40" y="33" font-size="14" fill="#374151">label transition</text>
  </g>

  <rect x="${margin.left}" y="${labelTop - 26}" width="${plotWidth}" height="${labelHeight + 34}" fill="#ffffff" stroke="#d9dee7"/>
  ${smokeBand}
  ${transitionLines}
  <line x1="${margin.left}" y1="${labelY("cigarette_smoke")}" x2="${width - margin.right}" y2="${labelY("cigarette_smoke")}" stroke="#e5e7eb"/>
  <line x1="${margin.left}" y1="${labelY("normal_air")}" x2="${width - margin.right}" y2="${labelY("normal_air")}" stroke="#e5e7eb"/>
  <text x="${margin.left - 12}" y="${labelY("cigarette_smoke") + 5}" text-anchor="end" font-size="13" fill="#374151">smoke</text>
  <text x="${margin.left - 12}" y="${labelY("normal_air") + 5}" text-anchor="end" font-size="13" fill="#374151">normal</text>
  ${labelSegments}
  ${labelText}

  ${seriesPanels}
  ${transitionLines}
  ${ticks}
  ${smokeBoundaryMarkers}
</svg>
`;
}

function writeHtml(svg) {
  const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SmokeLens cigarette smoke window</title>
  <style>
    body { margin: 0; background: #eef2f7; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { max-width: 1280px; margin: 0 auto; padding: 24px; }
    svg { width: 100%; height: auto; box-shadow: 0 16px 48px rgba(15, 23, 42, 0.14); }
  </style>
</head>
<body>
  <main>
${svg}
  </main>
</body>
</html>
`;
  fs.writeFileSync(path.join(OUTPUT_DIR, "index.html"), html);
}

function writeSummary(rows) {
  const runs = labelRuns(rows);
  const lines = [
    "# Cigarette Smoke Window Plot",
    "",
    "## Codex Handoff Summary",
    "",
    "Purpose:",
    "",
    "- Build a compact visualization that shows one clean `normal_air -> cigarette_smoke -> normal_air` transition from `data/smokelens.csv`.",
    "- The chart should be presentation-ready and should reflect the values actually shown on the dashboard.",
    "",
    "Current branch work:",
    "",
    "- Created this analysis folder and reproducible generator.",
    "- Selected a clear transition window from 2026-06-15 after 13:00 UTC+8.",
    "- Generated `window.csv`, `smoke_window.svg`, and `index.html`.",
    "- Changed the plot from model mV features to dashboard display fields.",
    "- Fixed a CSV parsing bug caused by empty inference columns before `cigarette_detected`; parser now locates `model_version` and reads sensor fields relative to that position.",
    "- Made the label timeline thinner and the whole SVG more compact.",
    "- Moved the legend to the top-right.",
    "- Left-side series labels are right-aligned outside the plotting area so text does not enter the panels.",
    "- X-axis tick labels use UTC+8 time-of-day format, including origin `14:34:40`.",
    "- Red downward arrows mark the cigarette smoke boundary times only: `14:35:24` and `14:36:29`.",
    "",
    "Important constraints:",
    "",
    "- Do not commit or push these latest local chart/layout changes until the user explicitly says so.",
    "- Do not include `.DS_Store` or `analysis/.DS_Store`.",
    "- Dashboard VOC/CO display uses `voc_raw` and `co_raw`, not `voc_mv` / `co_mv`.",
    "- Model feature columns use `voc_mv` / `co_mv`, but this chart intentionally follows dashboard display values.",
    "- PM and climate fields should parse as `pm1_0`, `pm2_5`, `pm10`, `temperature`, `humidity`; if `pm1_0` is near 2890 or temperature is 2-96, the CSV columns are misaligned.",
    "",
    "Local status at handoff:",
    "",
    "- Latest generated SVG height is `790` for a compact layout.",
    "- The bottom `time of day, UTC+8` axis caption was removed.",
    "- The user is iterating visually; expect small layout/text refinements before commit.",
    "",
    "Selected window:",
    "",
    "```text",
    `timestamp: ${WINDOW_START} ~ ${WINDOW_END}`,
    "local time: 2026-06-15 14:34:40 ~ 14:37:10 UTC+8",
    "```",
    "",
    "Label runs:",
    "",
    "| label | timestamp start | timestamp end | rows |",
    "| --- | ---: | ---: | ---: |",
    ...runs.map((run) => `| ${run.label} | ${run.startTimestamp} | ${run.endTimestamp} | ${run.count} |`),
    "",
    "Dashboard values plotted:",
    "",
    ...DASHBOARD_SERIES.map((series) => `- \`${series.csv}\``),
    "",
    "Generated files:",
    "",
    "- `window.csv`: extracted rows used for the plot",
    "- `smoke_window.svg`: static chart",
    "- `index.html`: browser-friendly wrapper for the chart",
    "",
    "Shared analysis data:",
    "",
    "- `../data/datapool.csv`: shared analysis data for teammates.",
    "- It started as a copy of `data/datapool.csv`, then missing rows from the full SmokeLens log were appended.",
    "- Merge identity used `node_id,timestamp,mode,model_version,voc_raw,co_raw,pm1_0,pm2_5,pm10,temperature,humidity` instead of `id`, because `datapool.csv` already had duplicate `id` values.",
    "- The shared file lives under `analysis/` so teammates can use it for plotting even though root `data/*.csv` is ignored by `.gitignore`.",
    "",
    "Regenerate with:",
    "",
    "```sh",
    "node analysis/cigarette-smoke-window/generate_plot.js",
    "```",
    ""
  ];
  fs.writeFileSync(path.join(OUTPUT_DIR, "README.md"), lines.join("\n"));
}

const rows = parseRows();
if (rows.length === 0) {
  throw new Error("No inference rows found for selected window");
}

writeWindowCsv(rows);
const svg = buildSvg(rows);
fs.writeFileSync(path.join(OUTPUT_DIR, "smoke_window.svg"), svg);
writeHtml(svg);
writeSummary(rows);

console.log(`Wrote ${rows.length} rows and plot files to ${OUTPUT_DIR}`);
