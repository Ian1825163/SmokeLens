const MODEL_VERSION = "backend_rule_v0";
const VOC_RAW_THRESHOLD = 2820;
const CO_RAW_THRESHOLD = 3925;
const PM25_THRESHOLD = 25.0;
const CIGARETTE_SCORE_THRESHOLD = 0.65;

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizedExcess(value, threshold) {
  if (threshold <= 0 || value <= threshold) {
    return 0;
  }
  return Math.min((value - threshold) / threshold, 1);
}

function inferReading(reading) {
  const vocRaw = number(reading.voc_raw);
  const coRaw = number(reading.co_raw);
  const pm25 = number(reading.pm2_5);

  const vocScore = normalizedExcess(vocRaw, VOC_RAW_THRESHOLD);
  const coScore = normalizedExcess(coRaw, CO_RAW_THRESHOLD);
  const pmScore = normalizedExcess(pm25, PM25_THRESHOLD);
  const score = 0.45 * vocScore + 0.35 * coScore + 0.20 * pmScore;
  const cigaretteDetected =
    score >= CIGARETTE_SCORE_THRESHOLD ||
    (vocRaw >= VOC_RAW_THRESHOLD &&
      coRaw >= CO_RAW_THRESHOLD &&
      pm25 >= PM25_THRESHOLD);

  return {
    inference_class: cigaretteDetected ? "cigarette_smoke" : "normal_air",
    cigarette_detected: cigaretteDetected,
    inference_score: score,
    model_version: MODEL_VERSION,
    classification: cigaretteDetected ? "cigarette_smoke" : "normal_air"
  };
}

function classifyReading(reading) {
  if (reading && reading.mode === "inference") {
    return inferReading(reading).classification;
  }
  return "unclassified";
}

module.exports = {
  classifyReading,
  inferReading
};
