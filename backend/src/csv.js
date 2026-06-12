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
  "received_at"
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

module.exports = {
  READING_COLUMNS,
  rowToCsv
};
