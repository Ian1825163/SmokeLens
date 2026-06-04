const state = {
  history: [],
  latest: [],
  feed: [],
  websocketOpen: false
};

function latestReading() {
  return state.latest[0]?.latest || null;
}

function updateMetrics() {
  const total = state.latest.length;
  const online = state.latest.filter((item) => item.online).length;
  const latest = latestReading();

  document.getElementById("nodesOnline").textContent = `${online}/${total}`;
  document.getElementById("wsState").textContent = state.websocketOpen
    ? "WebSocket live"
    : "WebSocket offline";

  document.getElementById("modeValue").textContent = latest?.mode || "-";
  document.getElementById("labelValue").textContent =
    latest?.collection_label || latest?.inference_class || "-";
  document.getElementById("adminPm25").textContent = SmokeLens.formatNumber(
    latest?.pm2_5,
    0
  );
  document.getElementById("adminGas").textContent = latest
    ? `${SmokeLens.formatNumber(latest.voc_raw, 0)} / ${SmokeLens.formatNumber(latest.co_raw, 0)}`
    : "-";
  document.getElementById("adminInference").textContent =
    latest?.inference_class || latest?.classification || "-";
  document.getElementById("adminScore").textContent =
    latest?.inference_score === null || latest?.inference_score === undefined
      ? "-"
      : `score ${SmokeLens.formatNumber(latest.inference_score, 2)}`;
}

function updateTable() {
  const body = document.getElementById("nodeTable");
  if (!state.latest.length) {
    body.innerHTML = '<tr><td colspan="10" class="empty">Waiting for readings</td></tr>';
    return;
  }

  body.innerHTML = state.latest
    .map((status) => {
      const latest = status.latest;
      const readingStatus = SmokeLens.statusFromReading(latest, status.online);
      return `
        <tr>
          <td>${SmokeLens.escapeHtml(status.node_id)}</td>
          <td><span class="pill pill-${readingStatus.className}">${SmokeLens.escapeHtml(readingStatus.label)}</span></td>
          <td>${SmokeLens.escapeHtml(latest.mode || "-")}</td>
          <td>${SmokeLens.escapeHtml(latest.collection_label || "-")}</td>
          <td>${SmokeLens.formatNumber(latest.voc_raw, 0)}</td>
          <td>${SmokeLens.formatNumber(latest.co_raw, 0)}</td>
          <td>${SmokeLens.formatNumber(latest.pm2_5, 0)}</td>
          <td>${SmokeLens.formatNumber(latest.temperature, 1)}</td>
          <td>${SmokeLens.formatNumber(latest.humidity, 1)}</td>
          <td>${SmokeLens.ageText(latest.received_at)}</td>
        </tr>
      `;
    })
    .join("");
}

function drawTrend() {
  const canvas = document.getElementById("trendCanvas");
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const padding = 28;
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
    context.font = "14px system-ui";
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
    context.fillText(item.label, padding + index * 70, 16);
  });
}

function updateFeed() {
  const feed = document.getElementById("feed");
  document.getElementById("feedCount").textContent = String(state.feed.length);
  if (!state.feed.length) {
    feed.innerHTML = '<div class="empty">Waiting for MQTT readings</div>';
    return;
  }

  feed.innerHTML = state.feed
    .slice(0, 20)
    .map((reading) => {
      const status = SmokeLens.statusFromReading(reading, true);
      return `
        <div class="feed-row">
          <div class="row-head">
            <strong>${SmokeLens.escapeHtml(reading.node_id)}</strong>
            <span class="pill pill-${status.className}">${SmokeLens.escapeHtml(status.label)}</span>
          </div>
          <div class="subtle">${SmokeLens.formatTime(reading.timestamp)} · ${SmokeLens.escapeHtml(reading.mode || "-")} · PM2.5 ${SmokeLens.formatNumber(reading.pm2_5, 0)} · VOC ${SmokeLens.formatNumber(reading.voc_raw, 0)} · CO ${SmokeLens.formatNumber(reading.co_raw, 0)}</div>
        </div>
      `;
    })
    .join("");
}

async function refresh() {
  const [statusPayload, historyPayload] = await Promise.all([
    SmokeLens.apiGet("/api/status"),
    SmokeLens.apiGet("/api/history?limit=80")
  ]);
  state.latest = statusPayload.data || [];
  state.history = (historyPayload.data || []).slice().reverse();
  document.getElementById("lastUpdate").textContent = new Date().toLocaleTimeString();
  updateMetrics();
  updateTable();
  drawTrend();
}

async function init() {
  await refresh();
  const socket = SmokeLens.connectWebSocket((event) => {
    if (event.type === "hello") {
      refresh().catch((error) => console.warn(error));
    }
    if (event.type === "reading") {
      state.feed.unshift(event.data);
      state.feed = state.feed.slice(0, 50);
      state.history.push(event.data);
      refresh().catch((error) => console.warn(error));
      updateFeed();
    }
  });
  socket.addEventListener("open", () => {
    state.websocketOpen = true;
    updateMetrics();
  });
  socket.addEventListener("close", () => {
    state.websocketOpen = false;
    updateMetrics();
  });
  setInterval(() => refresh().catch((error) => console.warn(error)), 10000);
}

init().catch((error) => {
  document.getElementById("nodeTable").innerHTML =
    `<tr><td colspan="10" class="empty">${SmokeLens.escapeHtml(error.message)}</td></tr>`;
});
