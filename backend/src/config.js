const path = require("path");
const dotenv = require("dotenv");

dotenv.config({ path: path.resolve(__dirname, "..", ".env") });

const repoRoot = path.resolve(__dirname, "..", "..");
const defaultDataDir = path.join(repoRoot, "data");

function numberFromEnv(name, fallback) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) ? value : fallback;
}

function resolveOptionalPath(value, fallback) {
  if (!value) {
    return fallback;
  }
  return path.isAbsolute(value) ? value : path.resolve(__dirname, "..", value);
}

module.exports = {
  repoRoot,
  dataDir: defaultDataDir,
  dbPath: resolveOptionalPath(
    process.env.DB_PATH,
    path.join(defaultDataDir, "smokelens.sqlite")
  ),
  httpPort: numberFromEnv("HTTP_PORT", 3000),
  mqttUrl: process.env.MQTT_URL || "mqtt://localhost:1883",
  mqttTopic: process.env.MQTT_TOPIC || "smokelens/+/data",
  nodeTimeoutMs: numberFromEnv("NODE_TIMEOUT_MS", 30000),
  historyLimitDefault: numberFromEnv("HISTORY_LIMIT_DEFAULT", 500),
  historyLimitMax: numberFromEnv("HISTORY_LIMIT_MAX", 5000),
  exportLimitMax: numberFromEnv("EXPORT_LIMIT_MAX", 100000)
};
