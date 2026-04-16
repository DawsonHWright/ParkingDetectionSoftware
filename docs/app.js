const API_BASE = "http://35.239.3.208:3000";

// ADDED THIS because the old version only fetched status and rendered cards.
// The newer version still uses backend status, but it also builds a simple
// theater-style layout automatically from the returned spot IDs.
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

// ORIGINAL:
// async function fetchLayout() {
//   return fetchJson(`${API_BASE}/api/layout`);
// }

// CHANGED THIS the layout will be auto-generated from the spot IDs in status.
function fetchLayout() {
  return null;
}

// KEPT THIS because live parking status still comes from the backend.
// This is what tells the page which spaces exist and whether they are open or unavailable.
async function fetchStatus() {
  return fetchJson(`${API_BASE}/api/status`);
}

function formatTimestamp(ts) {
  if (!ts) return "--";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

// CHANGED THIS so the UI stays simple:
// free = green
// selected = yellow
// occupied/reserved = red -- open to changing colors
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

// ADDED THIS FOR keeping spot IDs in numeric order like S1, S2, S10.
// This matters because plain text sorting would put S10 before S2.
function sortSpotsById(spots) {
  return [...spots].sort((a, b) => {
    const aNum = Number(String(a.id).replace(/\D/g, "")) || 0;
    const bNum = Number(String(b.id).replace(/\D/g, "")) || 0;
    return aNum - bNum;
  });
}

// ADDED THIS FOR generating row labels like A, B, C.
// It helps create cleaner display labels on the auto-generated layout.
function rowLabel(index) {
  return String.fromCharCode(65 + index);
}

// ADDED THIS because we do not have a finalized manual lot map yet.
// This automatically builds a simple theater-style layout from however many
// spaces the backend returns, so the page does not depend on hard-coded
// spot positions or a separate layout file. -- something TOM wanted 
function buildAutoLayout(spots) {
  const sorted = sortSpotsById(spots);
  const total = sorted.length;

  const spotWidth = 90;
  const spotHeight = 55;
  const horizontalGap = 20;
  const rowGap = 80;
  const aisleWidth = 120;
  const leftMargin = 140;
  const topMargin = 110;
  const bottomPadding = 180;

  // CHANGED THIS because we do not want to hard-code 3 spots on each side.
  // This calculates a reasonable even number of spots per row automatically
  // based on how many spaces the backend returns.
  let spotsPerRow = Math.ceil(Math.sqrt(total));
  if (spotsPerRow < 4) spotsPerRow = 4;
  if (spotsPerRow > 8) spotsPerRow = 8;
  if (spotsPerRow % 2 !== 0) spotsPerRow += 1;

  const leftCols = spotsPerRow / 2;
  const rows = Math.max(1, Math.ceil(total / spotsPerRow));

  const leftBlockWidth = leftCols * spotWidth + (leftCols - 1) * horizontalGap;
  const rightBlockWidth = leftBlockWidth;

  const canvasWidth =
    leftMargin +
    leftBlockWidth +
    aisleWidth +
    rightBlockWidth +
    leftMargin;

  const canvasHeight = topMargin + rows * rowGap + bottomPadding;

  function getSpotPosition(index) {
    const row = Math.floor(index / spotsPerRow);
    const col = index % spotsPerRow;

    let x;

    if (col < leftCols) {
      x = leftMargin + col * (spotWidth + horizontalGap);
    } else {
      const rightCol = col - leftCols;
      x =
        leftMargin +
        leftBlockWidth +
        aisleWidth +
        rightCol * (spotWidth + horizontalGap);
    }

    const y = topMargin + row * rowGap;
    return { x, y, row, col };
  }

  const layoutSpots = sorted.map((spot, index) => {
    const pos = getSpotPosition(index);

    return {
      id: String(spot.id),
      label: `${rowLabel(pos.row)}${pos.col + 1}`,
      x: pos.x,
      y: pos.y,
      width: spotWidth,
      height: spotHeight,
      angle: 0,
      type: "standard"
    };
  });

  const aisleX = leftMargin + leftBlockWidth + (aisleWidth / 2) - 15;

  // ADDED THIS FOR creating the visual layout object the page expects.
  // This gives us a center aisle, entrance, exit, title, and all spot positions.
  return {
    cameraId: "lot-1",
    name: "Auto Parking Layout",
    canvas: {
      width: canvasWidth,
      height: canvasHeight
    },
    decorations: [
      {
        kind: "text",
        text: "PARKING LOT MAP",
        x: Math.max(40, Math.floor(canvasWidth / 2) - 150),
        y: 35,
        className: "lot-title"
      },
      {
        kind: "lane",
        x: 90,
        y: canvasHeight - 140,
        width: canvasWidth - 180,
        height: 70,
        className: "drive-lane"
      },
      {
        kind: "text",
        text: "ENTRANCE",
        x: 110,
        y: canvasHeight - 45,
        className: "entrance-text"
      },
      {
        kind: "text",
        text: "EXIT",
        x: canvasWidth - 190,
        y: canvasHeight - 45,
        className: "exit-text"
      },
      {
        kind: "lane",
        x: aisleX,
        y: topMargin - 20,
        width: 30,
        height: rows * rowGap + 40,
        className: "center-aisle"
      }
    ],
    spots: layoutSpots
  };
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

// ADDED THIS FOR drawing title, aisle, entrance, and exit decorations.
// These are part of the auto-generated layout so the page still feels like
// a parking map instead of a plain list of buttons.
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
// This version still creates positioned parking spots, but now the positions
// come from the auto-generated layout instead of a separate layout file.
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

  el.addEventListener("click", () => {
    if (state === "occupied" || state === "reserved") {
      alert("That space is unavailable.");
      return;
    }

    // ADDED THIS because you wanted a theater-style flow.
    // Clicking a free spot selects it first instead of reserving it immediately.
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
// It takes the auto-generated layout and the live status and combines them
// so each parking spot is placed correctly and colored by its current state.
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

  const statusMap = new Map((status.spots || []).map((spot) => [String(spot.id), spot]));

  for (const layoutSpot of layout.spots) {
    const statusSpot = statusMap.get(String(layoutSpot.id)) || {
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

// CHANGED THIS because the page no longer loads a layout from the backend.
// It now builds the layout automatically from the returned spot IDs,
// then uses the backend status to color and update the spots.
async function renderDashboard() {
  try {
    currentStatus = await fetchStatus();

    const spots = Array.isArray(currentStatus.spots) ? currentStatus.spots : [];

    // ADDED THIS because the layout is now auto-generated from live spots.
    currentLayout = buildAutoLayout(spots);

    const selectedStatus = spots.find((spot) => String(spot.id) === String(selectedSpotId));

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

// KEPT THIS as a backend call because releasing a reservation still belongs
// to the backend even though the layout is now generated on the frontend.
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

// ORIGINAL:
// renderStatus();
// setInterval(renderStatus, 3000);

// CHANGED THIS because the page now refreshes the full auto-generated layout
// and live status together instead of just refreshing the old card list.
renderDashboard();
setInterval(renderDashboard, 3000);