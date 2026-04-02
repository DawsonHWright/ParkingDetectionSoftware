const API_BASE = "http://35.239.3.208:3000";

async function fetchStatus() {
  const res = await fetch(`${API_BASE}/api/status`);
  if (!res.ok) {
    throw new Error("Failed to fetch status");
  }
  return res.json();
}

function formatTimestamp(ts) {
  if (!ts) return "--";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

function getVisualState(spot) {
  if (spot.occupied) return "occupied";
  if (spot.reservedBy) return "reserved";
  return "free";
}

function getDisplayLabel(spot) {
  if (spot.occupied) return "Occupied";
  if (spot.reservedBy) return "Reserved";
  return "Free";
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

function spotCardHtml(spot) {
  const state = getVisualState(spot);
  const label = getDisplayLabel(spot);
  const confidence = Number(spot.confidence ?? 0).toFixed(3);

  return `
    <div class="spot-card ${state}">
      <h3>Spot ${spot.id}</h3>
      <div class="badge ${state}">${label}</div>
      <p class="spot-meta"><strong>Reserved By:</strong> ${spot.reservedBy || "None"}</p>
      <p class="spot-meta"><strong>Reserved At:</strong> ${spot.reservedAt ? formatTimestamp(spot.reservedAt) : "N/A"}</p>
      <div class="spot-actions">
        ${
          !spot.occupied && !spot.reservedBy
            ? `<button class="reserve-btn" onclick="reserveSpot('${spot.id}')">Reserve Spot</button>`
            : spot.reservedBy
            ? `<button class="release-btn" onclick="releaseSpot('${spot.id}')">Release Reservation</button>`
            : `<button class="reserve-btn" disabled>Unavailable</button>`
        }
      </div>
    </div>
  `;
}

async function renderStatus() {
  try {
    const data = await fetchStatus();

    document.getElementById("cameraId").textContent = data.cameraId || "--";
    document.getElementById("timestamp").textContent = formatTimestamp(data.timestamp);

    const spots = Array.isArray(data.spots) ? data.spots : [];
    updateSummary(spots);

    const grid = document.getElementById("spotsGrid");
    if (spots.length === 0) {
      grid.innerHTML = `<p>No parking data yet. Start the detector or POST updates to the backend.</p>`;
      return;
    }

    grid.innerHTML = spots.map(spotCardHtml).join("");
  } catch (err) {
    console.error(err);
    document.getElementById("spotsGrid").innerHTML =
      `<p>Could not load parking data.</p>`;
  }
}

async function reserveSpot(id) {
  const name = document.getElementById("nameInput").value.trim();

  try {
    const res = await fetch(`${API_BASE}/api/reserve/${id}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ name })
    });

    const data = await res.json();
    if (!res.ok) {
      alert(data.message || "Could not reserve spot");
      return;
    }

    await renderStatus();
  } catch (err) {
    console.error(err);
    alert("Reservation failed");
  }
}

async function releaseSpot(id) {
  try {
    const res = await fetch(`${API_BASE}/api/release/${id}`, {
      method: "POST"
    });

    const data = await res.json();
    if (!res.ok) {
      alert(data.message || "Could not release spot");
      return;
    }

    await renderStatus();
  } catch (err) {
    console.error(err);
    alert("Release failed");
  }
}

document.getElementById("refreshBtn").addEventListener("click", renderStatus);

renderStatus();
setInterval(renderStatus, 3000);