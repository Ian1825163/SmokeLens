const fs = require("fs");
const path = require("path");
const initSqlJs = require("sql.js");

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

function booleanToInteger(value) {
  if (value === true || value === 1 || value === "true") {
    return 1;
  }
  if (value === false || value === 0 || value === "false") {
    return 0;
  }
  return null;
}

function toApiRow(row) {
  if (!row) {
    return null;
  }

  return {
    ...row,
    pms_valid: row.pms_valid === null ? null : Boolean(row.pms_valid),
    cigarette_detected:
      row.cigarette_detected === null ? null : Boolean(row.cigarette_detected)
  };
}

function boundedLimit(value, fallback, max) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return Math.min(Math.trunc(parsed), max);
}

function queryAll(db, sql, params = []) {
  const statement = db.prepare(sql);
  const rows = [];

  try {
    statement.bind(params);
    while (statement.step()) {
      rows.push(statement.getAsObject());
    }
  } finally {
    statement.free();
  }

  return rows;
}

function queryOne(db, sql, params = []) {
  return queryAll(db, sql, params)[0] || null;
}

function ensureColumn(db, tableName, columnName, definition) {
  const columns = queryAll(db, `PRAGMA table_info(${tableName})`).map(
    (column) => column.name
  );
  if (!columns.includes(columnName)) {
    db.run(`ALTER TABLE ${tableName} ADD COLUMN ${columnName} ${definition}`);
  }
}

async function openDatabase(config) {
  fs.mkdirSync(path.dirname(config.dbPath), { recursive: true });

  const sqlJsDist = path.dirname(require.resolve("sql.js/dist/sql-wasm.js"));
  const SQL = await initSqlJs({
    locateFile: (file) => path.join(sqlJsDist, file)
  });

  const initialData = fs.existsSync(config.dbPath)
    ? fs.readFileSync(config.dbPath)
    : undefined;
  const db = new SQL.Database(initialData);

  function persist() {
    const data = db.export();
    fs.writeFileSync(config.dbPath, Buffer.from(data));
  }

  db.run(`
    CREATE TABLE IF NOT EXISTS readings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      node_id TEXT NOT NULL,
      timestamp INTEGER NOT NULL,
      mode TEXT,
      collection_label TEXT,
      inference_class TEXT,
      cigarette_detected INTEGER,
      inference_score REAL,
      model_version TEXT,
      voc_raw INTEGER,
      co_raw INTEGER,
      voc_mv INTEGER,
      co_mv INTEGER,
      pm1_0 REAL,
      pm2_5 REAL,
      pm10 REAL,
      temperature REAL,
      humidity REAL,
      pms_valid INTEGER,
      classification TEXT DEFAULT 'unclassified',
      raw_payload TEXT NOT NULL,
      received_at INTEGER NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_readings_node_time
      ON readings(node_id, timestamp);

    CREATE INDEX IF NOT EXISTS idx_readings_received_at
      ON readings(received_at);
  `);

  ensureColumn(db, "readings", "mode", "TEXT");
  ensureColumn(db, "readings", "collection_label", "TEXT");
  ensureColumn(db, "readings", "inference_class", "TEXT");
  ensureColumn(db, "readings", "cigarette_detected", "INTEGER");
  ensureColumn(db, "readings", "inference_score", "REAL");
  ensureColumn(db, "readings", "model_version", "TEXT");
  persist();

  function saveReading(input) {
    const reading = {
      node_id: String(input.node_id || "unknown"),
      timestamp:
        nullableInteger(input.timestamp) || Math.floor(Date.now() / 1000),
      mode: input.mode ? String(input.mode) : null,
      collection_label: input.collection_label
        ? String(input.collection_label)
        : null,
      inference_class: input.inference_class ? String(input.inference_class) : null,
      cigarette_detected: booleanToInteger(input.cigarette_detected),
      inference_score: nullableNumber(input.inference_score),
      model_version: input.model_version ? String(input.model_version) : null,
      voc_raw: nullableInteger(input.voc_raw),
      co_raw: nullableInteger(input.co_raw),
      voc_mv: nullableInteger(input.voc_mv),
      co_mv: nullableInteger(input.co_mv),
      pm1_0: nullableNumber(input.pm1_0),
      pm2_5: nullableNumber(input.pm2_5),
      pm10: nullableNumber(input.pm10),
      temperature: nullableNumber(input.temperature),
      humidity: nullableNumber(input.humidity),
      pms_valid: booleanToInteger(input.pms_valid),
      classification: input.classification || "unclassified",
      raw_payload: input.raw_payload || "{}",
      received_at: input.received_at || Date.now()
    };

    db.run(
      `
        INSERT INTO readings (
          node_id,
          timestamp,
          mode,
          collection_label,
          inference_class,
          cigarette_detected,
          inference_score,
          model_version,
          voc_raw,
          co_raw,
          voc_mv,
          co_mv,
          pm1_0,
          pm2_5,
          pm10,
          temperature,
          humidity,
          pms_valid,
          classification,
          raw_payload,
          received_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `,
      [
        reading.node_id,
        reading.timestamp,
        reading.mode,
        reading.collection_label,
        reading.inference_class,
        reading.cigarette_detected,
        reading.inference_score,
        reading.model_version,
        reading.voc_raw,
        reading.co_raw,
        reading.voc_mv,
        reading.co_mv,
        reading.pm1_0,
        reading.pm2_5,
        reading.pm10,
        reading.temperature,
        reading.humidity,
        reading.pms_valid,
        reading.classification,
        reading.raw_payload,
        reading.received_at
      ]
    );

    const saved = queryOne(
      db,
      "SELECT * FROM readings WHERE id = last_insert_rowid()"
    );
    persist();
    return toApiRow(saved);
  }

  function latestReadings() {
    return queryAll(
      db,
      `
        SELECT *
        FROM readings
        WHERE id IN (
          SELECT MAX(id)
          FROM readings
          GROUP BY node_id
        )
        ORDER BY node_id
      `
    ).map(toApiRow);
  }

  function historyReadings(options = {}) {
    const where = [];
    const params = [];
    const limit = boundedLimit(
      options.limit,
      config.historyLimitDefault,
      options.maxLimit || config.historyLimitMax
    );

    if (options.nodeId) {
      where.push("node_id = ?");
      params.push(String(options.nodeId));
    }

    if (options.from !== undefined) {
      const from = nullableInteger(options.from);
      if (from !== null) {
        where.push("timestamp >= ?");
        params.push(from);
      }
    }

    if (options.to !== undefined) {
      const to = nullableInteger(options.to);
      if (to !== null) {
        where.push("timestamp <= ?");
        params.push(to);
      }
    }

    const whereSql = where.length > 0 ? `WHERE ${where.join(" AND ")}` : "";
    const orderSql = options.ascending
      ? "ORDER BY timestamp ASC, id ASC"
      : "ORDER BY timestamp DESC, id DESC";

    return queryAll(
      db,
      `
        SELECT *
        FROM readings
        ${whereSql}
        ${orderSql}
        LIMIT ?
      `,
      [...params, limit]
    ).map(toApiRow);
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

  return {
    db,
    close: () => db.close(),
    saveReading,
    latestReadings,
    historyReadings,
    statusReadings
  };
}

module.exports = {
  openDatabase
};
