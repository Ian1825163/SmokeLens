const fs = require("fs");
const path = require("path");

const { READING_COLUMNS, parseCsv, rowToCsv } = require("./csv");

const INTEGER_COLUMNS = new Set([
  "id",
  "timestamp",
  "voc_raw",
  "co_raw",
  "voc_mv",
  "co_mv",
  "received_at"
]);
const NUMBER_COLUMNS = new Set([
  "inference_score",
  "pm1_0",
  "pm2_5",
  "pm10",
  "temperature",
  "humidity"
]);
const BOOLEAN_COLUMNS = new Set(["cigarette_detected", "pms_valid"]);

function nullableNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function nullableInteger(value) {
  const number = nullableNumber(value);
  return number === null ? null : Math.trunc(number);
}

function nullableBoolean(value) {
  if (value === true || value === 1 || value === "1" || value === "true") {
    return true;
  }
  if (value === false || value === 0 || value === "0" || value === "false") {
    return false;
  }
  return null;
}

function nullableText(value) {
  return value === null || value === undefined || value === ""
    ? null
    : String(value);
}

function normalizeRow(input) {
  const row = {};
  for (const column of READING_COLUMNS) {
    const value = input[column];
    if (INTEGER_COLUMNS.has(column)) {
      row[column] = nullableInteger(value);
    } else if (NUMBER_COLUMNS.has(column)) {
      row[column] = nullableNumber(value);
    } else if (BOOLEAN_COLUMNS.has(column)) {
      row[column] = nullableBoolean(value);
    } else {
      row[column] = nullableText(value);
    }
  }
  return row;
}

function boundedLimit(value, fallback, max) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return Math.min(Math.trunc(parsed), max);
}

function metricSummary(rows, column) {
  const values = rows
    .map((row) => nullableNumber(row[column]))
    .filter((value) => value !== null);
  if (values.length === 0) {
    return { mean: null, stddev: null };
  }

  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance =
    values.reduce((sum, value) => sum + (value - mean) ** 2, 0) /
    values.length;
  return { mean, stddev: Math.sqrt(Math.max(variance, 0)) };
}

function openStore(config) {
  fs.mkdirSync(path.dirname(config.csvPath), { recursive: true });

  let rows = [];
  if (fs.existsSync(config.csvPath)) {
    const contents = fs.readFileSync(config.csvPath, "utf8");
    if (contents.trim()) {
      rows = parseCsv(contents).map(normalizeRow);
    } else {
      fs.writeFileSync(config.csvPath, `${READING_COLUMNS.join(",")}\n`, "utf8");
    }
  } else {
    fs.writeFileSync(config.csvPath, `${READING_COLUMNS.join(",")}\n`, "utf8");
  }

  let nextId = rows.reduce((max, row) => Math.max(max, row.id || 0), 0) + 1;

  function saveReading(input) {
    const row = normalizeRow({
      ...input,
      id: nextId,
      node_id: input.node_id || "unknown",
      timestamp: nullableInteger(input.timestamp) || Math.floor(Date.now() / 1000),
      classification: input.classification || "unclassified",
      received_at: nullableInteger(input.received_at) || Date.now(),
      created_at: input.created_at || new Date().toISOString()
    });
    nextId += 1;
    fs.appendFileSync(config.csvPath, `${rowToCsv(row)}\n`, "utf8");
    rows.push(row);
    return row;
  }

  function latestReadings() {
    const latest = new Map();
    for (const row of rows) {
      const current = latest.get(row.node_id);
      if (!current || row.id > current.id) {
        latest.set(row.node_id, row);
      }
    }
    return [...latest.values()].sort((left, right) =>
      left.node_id.localeCompare(right.node_id)
    );
  }

  function historyReadings(options = {}) {
    const limit = boundedLimit(
      options.limit,
      config.historyLimitDefault,
      options.maxLimit || config.historyLimitMax
    );
    const from = nullableInteger(options.from);
    const to = nullableInteger(options.to);
    const receivedFrom = nullableInteger(options.receivedFrom);
    const nodeId = options.nodeId ? String(options.nodeId) : null;

    const filtered = rows.filter(
      (row) =>
        (!nodeId || row.node_id === nodeId) &&
        (from === null || row.timestamp >= from) &&
        (to === null || row.timestamp <= to) &&
        (receivedFrom === null || row.received_at >= receivedFrom)
    );
    filtered.sort((left, right) => {
      const difference = left.timestamp - right.timestamp || left.id - right.id;
      return options.ascending ? difference : -difference;
    });
    return filtered.slice(0, limit);
  }

  function statusReadings(nodeTimeoutMs) {
    const now = Date.now();
    return latestReadings().map((row) => ({
      node_id: row.node_id,
      online: now - row.received_at <= nodeTimeoutMs,
      last_seen_ms: row.received_at,
      age_ms: now - row.received_at,
      latest: row
    }));
  }

  function baselineSummary(options = {}) {
    const mode = String(options.mode || "data_collection");
    const collectionLabel = String(options.collectionLabel || "normal_air");
    const nodeId = options.nodeId ? String(options.nodeId) : null;
    const matchingRows = rows.filter(
      (row) =>
        row.mode === mode &&
        row.collection_label === collectionLabel &&
        row.pms_valid === true &&
        row.pm2_5 !== null &&
        row.voc_raw !== null &&
        row.co_raw !== null &&
        (!nodeId || row.node_id === nodeId)
    );

    return {
      mode,
      collection_label: collectionLabel,
      node_id: nodeId,
      row_count: matchingRows.length,
      metrics: {
        pm2_5: metricSummary(matchingRows, "pm2_5"),
        voc_raw: metricSummary(matchingRows, "voc_raw"),
        co_raw: metricSummary(matchingRows, "co_raw")
      }
    };
  }

  return {
    close: () => {},
    baselineSummary,
    saveReading,
    latestReadings,
    historyReadings,
    statusReadings
  };
}

module.exports = {
  openStore
};
