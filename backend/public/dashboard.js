const state = {
  config: null,
  map: null,
  markers: new Map(),
  circles: new Map(),
  latest: new Map()
};

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
    <span>${SmokeLens.escapeHtml(status.node_id)} · ${SmokeLens.ageText(latest.received_at)} ago · PM2.5 ${SmokeLens.formatNumber(latest.pm2_5, 0)} ug/m3</span>
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
    <span>VOC ${SmokeLens.formatNumber(latest.voc_raw, 0)} · CO ${SmokeLens.formatNumber(latest.co_raw, 0)}</span>
  `;
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
      zoomControl: true
    }).setView([firstLocation.lat, firstLocation.lng], 17);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 20,
      attribution: "&copy; OpenStreetMap"
    }).addTo(state.map);
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
        radius: location.radius_m,
        weight: 2,
        opacity: 0.8,
        fillOpacity: 0.24
      }).addTo(state.map);
      state.circles.set(status.node_id, circle);
    }
    circle.setLatLng(latLng);
    circle.setRadius(location.radius_m);
    circle.setStyle({
      color: readingStatus.color,
      fillColor: readingStatus.color
    });

    let marker = state.markers.get(status.node_id);
    if (!marker) {
      marker = L.marker(latLng).addTo(state.map);
      state.markers.set(status.node_id, marker);
    }
    marker.setLatLng(latLng);
    marker.bindPopup(markerPopup(status, location, readingStatus));
  });

  if (bounds.length > 1) {
    state.map.fitBounds(bounds, { padding: [48, 48], maxZoom: 17 });
  } else if (bounds.length === 1) {
    state.map.setView(bounds[0], 17);
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
          <div class="subtle">${SmokeLens.escapeHtml(latest.mode || "-")} · ${SmokeLens.escapeHtml(latest.collection_label || latest.inference_class || "-")} · ${SmokeLens.ageText(latest.received_at)} ago</div>
        </div>
      `;
    })
    .join("");
}

async function refresh() {
  const payload = await SmokeLens.apiGet("/api/status");
  const statusRows = payload.data || [];
  state.latest = SmokeLens.latestMapFromStatus(statusRows);
  updateSummary(statusRows);
  updateMap(statusRows);
  updateNodeList(statusRows);
}

async function init() {
  state.config = await SmokeLens.apiGet("/api/config");
  await refresh();
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
