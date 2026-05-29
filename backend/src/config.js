const path = require("path");
const dotenv = require("dotenv");

dotenv.config({ path: path.resolve(__dirname, "..", ".env") });

const repoRoot = path.resolve(__dirname, "..", "..");
const defaultDataDir = path.join(repoRoot, "data");

function numberFromEnv(name, fallback) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) ? value : fallback;
}

function boolFromEnv(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || raw === "") {
    return fallback;
  }
  return ["1", "true", "yes", "on"].includes(String(raw).toLowerCase());
}

function resolveOptionalPath(value, fallback) {
  if (!value) {
    return fallback;
  }
  return path.isAbsolute(value) ? value : path.resolve(__dirname, "..", value);
}

function parseJsonEnv(name, fallback) {
  const raw = process.env[name];
  if (!raw) {
    return fallback;
  }

  try {
    return JSON.parse(raw);
  } catch (error) {
    console.warn(`[config] ignored invalid ${name}: ${error.message}`);
    return fallback;
  }
}

const defaultNodeLocations = {
  node_01: {
    name: "Node 01",
    lat: 25.0173,
    lng: 121.5398,
    radius_m: 80
  }
};

module.exports = {
  repoRoot,
  dataDir: defaultDataDir,
  dbPath: resolveOptionalPath(
    process.env.DB_PATH,
    path.join(defaultDataDir, "smokelens.sqlite")
  ),
  httpPort: numberFromEnv("HTTP_PORT", 3000),
  mqttUrl: process.env.MQTT_URL || "mqtt://localhost:1883",
  mqttUsername: process.env.MQTT_USERNAME || undefined,
  mqttPassword: process.env.MQTT_PASSWORD || undefined,
  mqttRejectUnauthorized: boolFromEnv("MQTT_REJECT_UNAUTHORIZED", true),
  mqttTopic: process.env.MQTT_TOPIC || "smokelens/+/data",
  nodeLocations: parseJsonEnv("NODE_LOCATIONS_JSON", defaultNodeLocations),
  nodeTimeoutMs: numberFromEnv("NODE_TIMEOUT_MS", 30000),
  historyLimitDefault: numberFromEnv("HISTORY_LIMIT_DEFAULT", 500),
  historyLimitMax: numberFromEnv("HISTORY_LIMIT_MAX", 5000),
  exportLimitMax: numberFromEnv("EXPORT_LIMIT_MAX", 100000)
};
