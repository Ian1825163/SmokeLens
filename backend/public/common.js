const SmokeLens = (() => {
  const DEFAULT_CENTER = { lat: 25.02171637333861, lng: 121.53665177465513 };
  const DEFAULT_RADIUS_M = 80;

  async function apiGet(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`${path} ${response.status}`);
    }
    return response.json();
  }

  function number(value, fallback = null) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function formatNumber(value, digits = 0) {
    const parsed = number(value);
    if (parsed === null) {
      return "-";
    }
    return parsed.toFixed(digits);
  }

  function formatTime(value) {
    const timestamp = number(value);
    if (timestamp === null) {
      return "-";
    }
    return new Date(timestamp * 1000).toLocaleTimeString();
  }

  function ageText(receivedAt) {
    const received = number(receivedAt);
    if (received === null) {
      return "-";
    }
    const seconds = Math.max(0, Math.round((Date.now() - received) / 1000));
    if (seconds < 60) {
      return `${seconds}s`;
    }
    return `${Math.round(seconds / 60)}m`;
  }

  function statusFromReading(reading, online = true) {
    if (!reading || !online) {
      return {
        key: "offline",
        label: "Offline",
        className: "offline",
        color: "#7b8580",
        intensity: 0
      };
    }

    const inferenceClass = String(
      reading.inference_class || reading.classification || ""
    );
    const collectionLabel = String(reading.collection_label || "");
    const predictedClass =
      inferenceClass && inferenceClass !== "unclassified"
        ? inferenceClass
        : collectionLabel;

    if (predictedClass === "cigarette_smoke") {
      return {
        key: "alert",
        label: "Cigarette smoke",
        className: "alert",
        color: "#d43d32",
        intensity: 1
      };
    }

    if (predictedClass === "cooking_fume" || predictedClass === "vehicle_exhaust") {
      return {
        key: "caution",
        label: predictedClass === "cooking_fume" ? "Cooking fume" : "Vehicle exhaust",
        className: "caution",
        color: predictedClass === "cooking_fume" ? "#c58b13" : "#d5662f",
        intensity: 0.55
      };
    }

    return {
      key: "normal",
      label: "Normal air",
      className: "normal",
      color: "#1f9d67",
      intensity: 0.15
    };
  }

  function nodeLocation(config, nodeId, index = 0) {
    const locations = (config && config.node_locations) || {};
    const location = locations[nodeId] || {};
    const offset = index * 0.0012;
    return {
      name: location.name || nodeId,
      lat: number(location.lat, DEFAULT_CENTER.lat + offset),
      lng: number(location.lng, DEFAULT_CENTER.lng + offset),
      radius_m: number(location.radius_m, DEFAULT_RADIUS_M)
    };
  }

  function connectWebSocket(onEvent) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}`);
    socket.addEventListener("message", (event) => {
      try {
        onEvent(JSON.parse(event.data));
      } catch (error) {
        console.warn("bad websocket message", error);
      }
    });
    return socket;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function latestMapFromStatus(statusRows) {
    const map = new Map();
    for (const status of statusRows || []) {
      if (status.latest) {
        map.set(status.node_id, status);
      }
    }
    return map;
  }

  return {
    ageText,
    apiGet,
    connectWebSocket,
    escapeHtml,
    formatNumber,
    formatTime,
    latestMapFromStatus,
    number,
    nodeLocation,
    statusFromReading
  };
})();
