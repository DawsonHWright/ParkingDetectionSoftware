const API_BASE = "http://35.239.3.208:3000";

// ADDED THIS because the old version only fetched status and rendered cards.
// The theater-style layout needs both the visual layout and the live spot status.
let currentLayout = null;
let currentStatus = null;
let selectedSpotId = null;

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);

  let data = null;
  try {
    data = await res.json();
  } catch (err) {
    data = null;
  }

  if (!res.ok) {
    throw new Error(data?.message || `Request failed: ${res.status}`);
  }

  return data;
}

// ADDED THIS FOR loading the parking lot layout blueprint.
async function fetchLayout() {
  return fetchJson(`${API_BASE}/api/layout`);
}

// KEPT / CHANGED THIS because status still comes from the backend,
// but now it is used to color spots on the map instead of making cards.
async function fetchStatus() {
  return fetchJson(`${API_BASE}/api/status`);
}

function formatTimestamp(ts) {
  if (!ts) return "--";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

// CHANGED THIS so reserved and occupied can both show as unavailable / red.
// Free stays green. Selected will be handled separately.
function getVisualState(spot) {
  if (spot.occupied) return "occupied";
  if (spot.reservedBy) return "reserved";
  return "free";
}

function updateSummary(spots) {
  const total = spots.length;
  const occupied = spots.filter((s) => s.occupied).length;
  const reserved = spots.filter((s) => !s.occupied && s.reservedBy).length;
  const free = spots.filter((s) => !s.occupied && !s.reservedBy).length;

  document.getElementById("totalSpots").textContent = total;
  document.getElementById("occupiedSpots").textContent = occupied;
  document.getElementById("reservedSpots").textContent = reserved;
  document.getElementById("freeSpots").textContent = free;
}

function updateSelectedLabel(layout, selectedId) {
  const labelEl = document.getElementById("selectedSpotLabel");

  if (!selectedId || !layout) {
    labelEl.textContent = "None";
    return;
  }

  const spot = layout.spots.find((s) => s.id === selectedId);
  labelEl.textContent = spot ? `${spot.label} (${spot.id})` : selectedId;
}

// ADDED THIS FOR drawing entrance / exit / aisle decorations from lotlayout.json.
function createDecorationElement(item) {
  const el = document.createElement("div");
  el.className = `lot-decoration ${item.className || ""}`;

  if (item.kind === "text") {
    el.textContent = item.text || "";
    el.style.left = `${item.x}px`;
    el.style.top = `${item.y}px`;
  }

  if (item.kind === "lane") {
    el.style.left = `${item.x}px`;
    el.style.top = `${item.y}px`;
    el.style.width = `${item.width}px`;
    el.style.height = `${item.height}px`;
  }

  return el;
}

// CHANGED THIS because the old version created cards.
// This now creates positioned parking spaces like theater seats.
function createSpotElement(layoutSpot, statusSpot) {
  const state = getVisualState(statusSpot);
  const isSelected = selectedSpotId === layoutSpot.id && state === "free";

  const el = document.createElement("button");
  el.type = "button";
  el.className = `lot-spot ${state} ${isSelected ? "selected" : ""} ${layoutSpot.type || "standard"}`;
  el.style.left = `${layoutSpot.x}px`;
  el.style.top = `${layoutSpot.y}px`;
  el.style.width = `${layoutSpot.width}px`;
  el.style.height = `${layoutSpot.height}px`;
  el.style.transform = `rotate(${layoutSpot.angle || 0}deg)`;

  el.innerHTML = `
    <span class="spot-label">${layoutSpot.label}</span>
    <span class="spot-id">${layoutSpot.id}</span>
  `;

  const reservedBy = statusSpot.reservedBy || "None";
  const reservedAt = statusSpot.reservedAt ? formatTimestamp(statusSpot.reservedAt) : "N/A";
  const confidence = Number(statusSpot.confidence ?? 0).toFixed(3);

  el.title = [
    `Spot: ${layoutSpot.id}`,
    `Label: ${layoutSpot.label}`,
    `State: ${state}`,
    `Reserved By: ${reservedBy}`,
    `Reserved At: ${reservedAt}`,
    `Confidence: ${confidence}`
  ].join("\n");

  el.addEventListener("click", async () => {
    if (state === "occupied" || state === "reserved") {
      alert("That space is unavailable.");
      return;
    }

    // ADDED THIS so clicking a free spot highlights it yellow instead of reserving immediately.
    if (selectedSpotId === layoutSpot.id) {
      selectedSpotId = null;
    } else {
      selectedSpotId = layoutSpot.id;
    }

    updateSelectedLabel(currentLayout, selectedSpotId);
    renderLot(currentLayout, currentStatus);
  });

  return el;
}

// ADDED THIS FOR drawing the theater-style parking layout.
function renderLot(layout, status) {
  const canvas = document.getElementById("lotCanvas");
  canvas.innerHTML = "";
  canvas.style.width = `${layout.canvas.width}px`;
  canvas.style.height = `${layout.canvas.height}px`;

  if (Array.isArray(layout.decorations)) {
    for (const item of layout.decorations) {
      canvas.appendChild(createDecorationElement(item));
    }
  }

  const statusMap = new Map(status.spots.map((spot) => [spot.id, spot]));

  for (const layoutSpot of layout.spots) {
    const statusSpot = statusMap.get(layoutSpot.id) || {
      id: layoutSpot.id,
      occupied: false,
      confidence: 0,
      reservedBy: null,
      reservedAt: null
    };

    const spotEl = createSpotElement(layoutSpot, statusSpot);
    canvas.appendChild(spotEl);
  }
}

// CHANGED THIS because the page now has to load both layout + live status.
async function renderDashboard() {
  try {
    if (!currentLayout) {
      currentLayout = await fetchLayout();
    }

    currentStatus = await fetchStatus();

    const spots = Array.isArray(currentStatus.spots) ? currentStatus.spots : [];
    const selectedStatus = spots.find((spot) => spot.id === selectedSpotId);

    if (selectedStatus && (selectedStatus.occupied || selectedStatus.reservedBy)) {
      selectedSpotId = null;
    }

    document.getElementById("cameraId").textContent = currentStatus.cameraId || "--";
    document.getElementById("timestamp").textContent = formatTimestamp(currentStatus.timestamp);

    updateSummary(spots);
    updateSelectedLabel(currentLayout, selectedSpotId);
    renderLot(currentLayout, currentStatus);
  } catch (err) {
    console.error(err);
    document.getElementById("lotCanvas").innerHTML = `<p>Could not load parking lot data.</p>`;
  }
}

// ADDED THIS because the old version reserved on click.
// Now a user selects first, then confirms reservation with the button.
async function reserveSelectedSpot() {
  if (!selectedSpotId) {
    alert("Select a parking space first.");
    return;
  }

  const name = document.getElementById("nameInput").value.trim();
  if (!name) {
    alert("Enter your name first.");
    return;
  }

  try {
    await fetchJson(`${API_BASE}/api/reserve/${selectedSpotId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ name })
    });

    selectedSpotId = null;
    await renderDashboard();
  } catch (err) {
    console.error(err);
    alert(err.message || "Reservation failed");
  }
}

// KEPT THIS as a backend call, but now it is not tied to clicking unavailable spots.
async function releaseSpot(id) {
  try {
    await fetchJson(`${API_BASE}/api/release/${id}`, {
      method: "POST"
    });

    if (selectedSpotId === id) {
      selectedSpotId = null;
    }

    await renderDashboard();
  } catch (err) {
    console.error(err);
    alert(err.message || "Release failed");
  }
}

document.getElementById("refreshBtn").addEventListener("click", renderDashboard);
document.getElementById("reserveBtn").addEventListener("click", reserveSelectedSpot);
document.getElementById("clearSelectionBtn").addEventListener("click", () => {
  selectedSpotId = null;
  updateSelectedLabel(currentLayout, selectedSpotId);
  renderLot(currentLayout, currentStatus);
});

renderDashboard();
setInterval(renderDashboard, 3000);