const READING_COLUMNS = [
  "id",
  "node_id",
  "timestamp",
  "mode",
  "collection_label",
  "trial_state",
  "inference_class",
  "event_marker",
  "cigarette_detected",
  "inference_score",
  "model_version",
  "voc_raw",
  "co_raw",
  "voc_mv",
  "co_mv",
  "pm1_0",
  "pm2_5",
  "pm10",
  "temperature",
  "humidity",
  "pms_valid",
  "classification",
  "raw_payload",
  "received_at",
  "created_at"
];

function csvEscape(value) {
  if (value === null || value === undefined) {
    return "";
  }

  const text = String(value);
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function rowToCsv(row) {
  return READING_COLUMNS.map((column) => csvEscape(row[column])).join(",");
}

function parseCsv(text) {
  if (!text.trim()) {
    return [];
  }

  const records = [];
  let record = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        field += character;
      }
    } else if (character === '"') {
      quoted = true;
    } else if (character === ",") {
      record.push(field);
      field = "";
    } else if (character === "\n") {
      record.push(field.replace(/\r$/, ""));
      records.push(record);
      record = [];
      field = "";
    } else {
      field += character;
    }
  }

  if (field || record.length > 0) {
    record.push(field.replace(/\r$/, ""));
    records.push(record);
  }

  const [header, ...data] = records;
  if (!header) {
    return [];
  }
  header[0] = header[0].replace(/^\uFEFF/, "");
  return data
    .filter((values) => values.some((value) => value !== ""))
    .map((values) =>
      Object.fromEntries(header.map((column, index) => [column, values[index] || ""]))
    );
}

module.exports = {
  READING_COLUMNS,
  parseCsv,
  rowToCsv
};
