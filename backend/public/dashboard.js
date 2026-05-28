const state = {
  config: null,
  map: null,
  fitKey: "",
  markers: new Map(),
  circles: new Map(),
  latest: new Map(),
  history: []
};

const MAP_RADIUS_SCALE = 0.25;
const MIN_VISIBLE_RADIUS_M = 12;

function displayRadiusMeters(location) {
  return Math.max(MIN_VISIBLE_RADIUS_M, location.radius_m * MAP_RADIUS_SCALE);
}

function strongestStatus(statusRows) {
  let best = null;
  for (const status of statusRows) {
    const readingStatus = SmokeLens.statusFromReading(status.latest, status.online);
    if (!best || readingStatus.intensity > best.readingStatus.intensity) {
      best = { status, readingStatus };
    }
  }
  return best;
}

function statusClass(status) {
  return `status-banner status-${status.className}`;
}

function pillClass(status) {
  return `pill pill-${status.className}`;
}

function updateSummary(statusRows) {
  const areaStatus = document.getElementById("areaStatus");
  const best = strongestStatus(statusRows);

  if (!best) {
    areaStatus.className = "status-banner status-offline";
    areaStatus.innerHTML = "<strong>Waiting for data</strong><span>No live reading yet</span>";
    return;
  }

  const { status, readingStatus } = best;
  const latest = status.latest;
  areaStatus.className = statusClass(readingStatus);
  areaStatus.innerHTML = `
    <strong>${SmokeLens.escapeHtml(readingStatus.label)}</strong>
    <span>${SmokeLens.escapeHtml(status.node_id)} &middot; ${SmokeLens.ageText(latest.received_at)} ago &middot; PM2.5 ${SmokeLens.formatNumber(latest.pm2_5, 0)} ug/m3</span>
  `;

  document.getElementById("pm25Value").textContent = SmokeLens.formatNumber(latest.pm2_5, 0);
  document.getElementById("humidityValue").textContent = SmokeLens.formatNumber(latest.humidity, 1);
  document.getElementById("vocValue").textContent = SmokeLens.formatNumber(latest.voc_raw, 0);
  document.getElementById("coValue").textContent = SmokeLens.formatNumber(latest.co_raw, 0);
}

function markerPopup(status, location, readingStatus) {
  const latest = status.latest;
  return `
    <strong>${SmokeLens.escapeHtml(location.name)}</strong><br>
    <span>${SmokeLens.escapeHtml(readingStatus.label)}</span><br>
    <span>PM2.5 ${SmokeLens.formatNumber(latest.pm2_5, 0)} ug/m3</span><br>
    <span>VOC ${SmokeLens.formatNumber(latest.voc_raw, 0)} &middot; CO ${SmokeLens.formatNumber(latest.co_raw, 0)}</span>
  `;
}

function resizeMapSoon() {
  if (!state.map) {
    return;
  }

  [0, 120, 350].forEach((delayMs) => {
    setTimeout(() => {
      if (state.map) {
        state.map.invalidateSize();
      }
    }, delayMs);
  });
}

function ensureMap(statusRows) {
  if (!window.L) {
    document.getElementById("map").innerHTML =
      '<div class="empty">Map library unavailable</div>';
    return;
  }

  if (!state.map) {
    const firstNode = statusRows[0]?.node_id || "node_01";
    const firstLocation = SmokeLens.nodeLocation(state.config, firstNode, 0);
    state.map = L.map("map", {
      zoomControl: false
    }).setView([firstLocation.lat, firstLocation.lng], 17);
    L.control.zoom({ position: "bottomleft" }).addTo(state.map);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 20,
      attribution: "&copy; OpenStreetMap"
    }).addTo(state.map);

    resizeMapSoon();
  }
}

function updateMap(statusRows) {
  ensureMap(statusRows);
  if (!state.map || !window.L) {
    return;
  }

  const bounds = [];
  statusRows.forEach((status, index) => {
    const location = SmokeLens.nodeLocation(state.config, status.node_id, index);
    const latest = status.latest;
    const readingStatus = SmokeLens.statusFromReading(latest, status.online);
    const latLng = [location.lat, location.lng];
    bounds.push(latLng);

    let circle = state.circles.get(status.node_id);
    if (!circle) {
      circle = L.circle(latLng, {
        radius: displayRadiusMeters(location),
        weight: 2,
        opacity: 0.8,
        fillOpacity: 0.24
      }).addTo(state.map);
      state.circles.set(status.node_id, circle);
    }
    circle.setLatLng(latLng);
    circle.setRadius(displayRadiusMeters(location));
    circle.setStyle({
      color: readingStatus.color,
      fillColor: readingStatus.color
    });

    let marker = state.markers.get(status.node_id);
    if (!marker) {
      marker = L.circleMarker(latLng, {
        color: "#ffffff",
        fillOpacity: 1,
        radius: 8,
        weight: 3
      }).addTo(state.map);
      state.markers.set(status.node_id, marker);
    }
    marker.setLatLng(latLng);
    marker.setStyle({
      fillColor: readingStatus.color
    });
    marker.bindPopup(markerPopup(status, location, readingStatus));
  });

  const fitKey = bounds.map((point) => point.join(",")).join("|");
  if (fitKey && fitKey !== state.fitKey) {
    state.fitKey = fitKey;
    if (bounds.length > 1) {
      state.map.fitBounds(bounds, { padding: [48, 48], maxZoom: 17 });
    } else {
      state.map.setView(bounds[0], 17);
    }
    resizeMapSoon();
  }
}

function updateNodeList(statusRows) {
  const nodeList = document.getElementById("nodeList");
  if (!statusRows.length) {
    nodeList.innerHTML = '<div class="empty">Waiting for nodes</div>';
    return;
  }

  nodeList.innerHTML = statusRows
    .map((status) => {
      const latest = status.latest;
      const readingStatus = SmokeLens.statusFromReading(latest, status.online);
      const activeClass = readingStatus.key === "alert" ? " active" : "";
      return `
        <div class="node-row${activeClass}">
          <div class="row-head">
            <strong>${SmokeLens.escapeHtml(status.node_id)}</strong>
            <span class="${pillClass(readingStatus)}">${SmokeLens.escapeHtml(readingStatus.label)}</span>
          </div>
          <div class="subtle">${SmokeLens.escapeHtml(latest.mode || "-")} &middot; ${SmokeLens.escapeHtml(latest.collection_label || latest.inference_class || "-")} &middot; ${SmokeLens.ageText(latest.received_at)} ago</div>
        </div>
      `;
    })
    .join("");
}

function setupCanvas(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(320, Math.round(rect.width * ratio));
  const height = Math.max(160, Math.round(rect.height * ratio));

  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }

  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return {
    context,
    width: width / ratio,
    height: height / ratio
  };
}

function drawTrend() {
  const canvas = document.getElementById("userTrendCanvas");
  if (!canvas) {
    return;
  }

  const { context, width, height } = setupCanvas(canvas);
  const padding = 26;
  const rows = state.history.slice(-60);

  context.clearRect(0, 0, width, height);
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, height);

  context.strokeStyle = "#d9dfd9";
  context.lineWidth = 1;
  for (let i = 0; i < 4; i++) {
    const y = padding + ((height - padding * 2) * i) / 3;
    context.beginPath();
    context.moveTo(padding, y);
    context.lineTo(width - padding, y);
    context.stroke();
  }

  if (rows.length < 2) {
    context.fillStyle = "#64706b";
    context.font = "13px system-ui";
    context.fillText("Waiting for trend data", padding, height / 2);
    return;
  }

  const series = [
    { key: "pm2_5", color: "#2f6ea9", label: "PM2.5" },
    { key: "voc_raw", color: "#1f9d67", label: "VOC" },
    { key: "co_raw", color: "#d5662f", label: "CO" }
  ];

  series.forEach((item, index) => {
    const values = rows.map((row) => Number(row[item.key]) || 0);
    const max = Math.max(...values, 1);
    context.strokeStyle = item.color;
    context.lineWidth = 2;
    context.beginPath();

    values.forEach((value, valueIndex) => {
      const x =
        padding +
        ((width - padding * 2) * valueIndex) / Math.max(values.length - 1, 1);
      const y =
        height -
        padding -
        ((height - padding * 2) * value) / max;
      if (valueIndex === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    });

    context.stroke();
    context.fillStyle = item.color;
    context.font = "12px system-ui";
    context.fillText(item.label, padding + index * 62, 16);
  });
}

async function refresh() {
  const [statusPayload, historyPayload] = await Promise.all([
    SmokeLens.apiGet("/api/status"),
    SmokeLens.apiGet("/api/history?limit=80")
  ]);
  const statusRows = statusPayload.data || [];
  state.latest = SmokeLens.latestMapFromStatus(statusRows);
  state.history = (historyPayload.data || []).slice().reverse();
  updateSummary(statusRows);
  updateMap(statusRows);
  updateNodeList(statusRows);
  drawTrend();
}

async function init() {
  state.config = await SmokeLens.apiGet("/api/config");
  await refresh();
  window.addEventListener("resize", () => {
    resizeMapSoon();
    drawTrend();
  });
  SmokeLens.connectWebSocket((event) => {
    if (event.type === "hello" || event.type === "reading") {
      refresh().catch((error) => console.warn(error));
    }
  });
  setInterval(() => refresh().catch((error) => console.warn(error)), 10000);
}

init().catch((error) => {
  document.getElementById("areaStatus").className = "status-banner status-offline";
  document.getElementById("areaStatus").innerHTML = `<strong>Dashboard error</strong><span>${SmokeLens.escapeHtml(error.message)}</span>`;
});
