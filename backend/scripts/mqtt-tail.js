#!/usr/bin/env node

const mqtt = require("mqtt");
const config = require("../src/config");

function parseArgs(argv) {
  const args = {
    mqttUrl: config.mqttUrl,
    topic: config.mqttTopic,
    raw: false
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--raw") {
      args.raw = true;
    } else if (arg === "--mqtt-url") {
      args.mqttUrl = argv[index + 1] || args.mqttUrl;
      index += 1;
    } else if (arg === "--topic") {
      args.topic = argv[index + 1] || args.topic;
      index += 1;
    } else if (arg === "--help" || arg === "-h") {
      args.help = true;
    }
  }

  return args;
}

function printHelp() {
  console.log(`Usage: npm run mqtt:tail -- [options]

Options:
  --raw                 Print raw MQTT JSON payloads.
  --mqtt-url <url>      MQTT broker URL. Default: ${config.mqttUrl}
  --topic <topic>       MQTT topic filter. Default: ${config.mqttTopic}
  --help, -h            Show this help text.
`);
}

function number(value, digits = 0) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return "-";
  }
  return parsed.toFixed(digits);
}

function boolText(value) {
  return value === true || value === 1 || value === "true" ? "true" : "false";
}

function formatTime(reading) {
  const timestamp = Number(reading.timestamp);
  if (Number.isFinite(timestamp) && timestamp > 1700000000) {
    return new Date(timestamp * 1000).toLocaleTimeString();
  }
  return new Date().toLocaleTimeString();
}

function formatReading(topic, reading) {
  const nodeId = reading.node_id || topic.split("/")[1] || "unknown";
  const mode = reading.mode || "-";
  const label = reading.collection_label || reading.inference_class || "-";
  const pmsValid = boolText(reading.pms_valid);

  return [
    `[${formatTime(reading)}]`,
    nodeId,
    `mode=${mode}`,
    `label=${label}`,
    `pm=${number(reading.pm1_0)}/${number(reading.pm2_5)}/${number(reading.pm10)}`,
    `temp=${number(reading.temperature, 1)}C`,
    `rh=${number(reading.humidity, 1)}%`,
    `voc=${number(reading.voc_raw)}`,
    `co=${number(reading.co_raw)}`,
    `pms=${pmsValid}`
  ].join(" ");
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    printHelp();
    return;
  }

  const client = mqtt.connect(args.mqttUrl, {
    reconnectPeriod: 2000
  });

  client.on("connect", () => {
    console.log(`[mqtt-tail] connected ${args.mqttUrl}`);
    client.subscribe(args.topic, { qos: 0 }, (error) => {
      if (error) {
        console.error(`[mqtt-tail] subscribe failed: ${error.message}`);
        return;
      }
      console.log(`[mqtt-tail] subscribed ${args.topic}`);
    });
  });

  client.on("message", (topic, payload) => {
    const text = payload.toString("utf8");
    if (args.raw) {
      console.log(text);
      return;
    }

    try {
      console.log(formatReading(topic, JSON.parse(text)));
    } catch (error) {
      console.log(`[${new Date().toLocaleTimeString()}] ${topic} ${text}`);
    }
  });

  client.on("reconnect", () => {
    console.log("[mqtt-tail] reconnecting");
  });

  client.on("error", (error) => {
    console.error(`[mqtt-tail] ${error.message}`);
  });

  process.on("SIGINT", () => {
    console.log("\n[mqtt-tail] closing");
    client.end(true, () => process.exit(0));
  });
}

main();
