const http = require("http");
const express = require("express");
const mqtt = require("mqtt");
const { WebSocketServer, WebSocket } = require("ws");

const config = require("./config");
const { classifyReading } = require("./classifier");
const { openDatabase } = require("./db");
const { READING_COLUMNS, rowToCsv } = require("./csv");

function topicNodeId(topic) {
  const parts = String(topic).split("/");
  if (parts.length >= 3 && parts[0] === "smokelens" && parts[2] === "data") {
    return parts[1];
  }
  return null;
}

function buildReading(topic, payloadBuffer) {
  const rawPayload = payloadBuffer.toString("utf8");
  let parsed;

  try {
    parsed = JSON.parse(rawPayload);
  } catch (error) {
    console.warn(`[mqtt] dropped invalid JSON on ${topic}: ${error.message}`);
    return null;
  }

  const reading = {
    ...parsed,
    node_id: parsed.node_id || topicNodeId(topic) || "unknown",
    raw_payload: rawPayload,
    received_at: Date.now()
  };

  if (!reading.classification) {
    reading.classification = classifyReading(reading);
  }

  return reading;
}

function broadcast(wss, event) {
  const message = JSON.stringify(event);
  for (const client of wss.clients) {
    if (client.readyState === WebSocket.OPEN) {
      client.send(message);
    }
  }
}

function registerRoutes(app, wss, store) {
  app.get("/", (req, res) => {
    res.json({
      service: "SmokeLens backend",
      endpoints: [
        "/api/health",
        "/api/latest",
        "/api/history?node_id=node_01&limit=100",
        "/api/status",
        "/api/export.csv"
      ],
      websocket: "/"
    });
  });

  app.get("/api/health", (req, res) => {
    res.json({
      ok: true,
      mqtt_url: config.mqttUrl,
      mqtt_topic: config.mqttTopic,
      db_path: config.dbPath,
      websocket_clients: wss.clients.size
    });
  });

  app.get("/api/latest", (req, res) => {
    res.json({
      data: store.latestReadings()
    });
  });

  app.get("/api/status", (req, res) => {
    res.json({
      data: store.statusReadings(config.nodeTimeoutMs)
    });
  });

  app.get("/api/history", (req, res) => {
    res.json({
      data: store.historyReadings({
        nodeId: req.query.node_id,
        from: req.query.from,
        to: req.query.to,
        limit: req.query.limit
      })
    });
  });

  app.get("/api/export.csv", (req, res) => {
    const rows = store.historyReadings({
      nodeId: req.query.node_id,
      from: req.query.from,
      to: req.query.to,
      limit: req.query.limit || config.exportLimitMax,
      maxLimit: config.exportLimitMax,
      ascending: true
    });

    res.setHeader("Content-Type", "text/csv; charset=utf-8");
    res.setHeader("Content-Disposition", "attachment; filename=smokelens.csv");
    res.write(`${READING_COLUMNS.join(",")}\n`);
    for (const row of rows) {
      res.write(`${rowToCsv(row)}\n`);
    }
    res.end();
  });
}

async function main() {
  const store = await openDatabase(config);
  const app = express();
  const server = http.createServer(app);
  const wss = new WebSocketServer({ server });

  app.use(express.json());
  app.use((req, res, next) => {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
    next();
  });

  registerRoutes(app, wss, store);

  wss.on("connection", (socket) => {
    socket.send(
      JSON.stringify({
        type: "hello",
        data: {
          latest: store.latestReadings()
        }
      })
    );
  });

  const mqttClient = mqtt.connect(config.mqttUrl, {
    clientId: `smokelens_backend_${Math.random().toString(16).slice(2)}`,
    reconnectPeriod: 5000
  });

  mqttClient.on("connect", () => {
    console.log(`[mqtt] connected ${config.mqttUrl}`);
    mqttClient.subscribe(config.mqttTopic, { qos: 0 }, (error) => {
      if (error) {
        console.error(`[mqtt] subscribe failed: ${error.message}`);
        return;
      }
      console.log(`[mqtt] subscribed ${config.mqttTopic}`);
    });
  });

  mqttClient.on("reconnect", () => {
    console.log("[mqtt] reconnecting");
  });

  mqttClient.on("error", (error) => {
    console.error(`[mqtt] ${error.message}`);
  });

  mqttClient.on("message", (topic, payload) => {
    const reading = buildReading(topic, payload);
    if (!reading) {
      return;
    }

    const saved = store.saveReading(reading);
    console.log(
      `[data] ${saved.node_id} ts=${saved.timestamp} voc=${saved.voc_raw} co=${saved.co_raw} pm25=${saved.pm2_5} pms=${saved.pms_valid}`
    );

    broadcast(wss, {
      type: "reading",
      data: saved
    });
  });

  server.listen(config.httpPort, "0.0.0.0", () => {
    console.log(`[http] listening on http://localhost:${config.httpPort}`);
    console.log(`[db] ${config.dbPath}`);
  });

  function shutdown() {
    console.log("[shutdown] closing services");
    mqttClient.end(true);
    server.close(() => {
      store.close();
      process.exit(0);
    });
  }

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
