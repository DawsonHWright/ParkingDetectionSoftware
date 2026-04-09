const express = require("express");
const fs = require("fs");
const path = require("path");
const cors = require("cors");


const app = express();
const PORT = 3000;

app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));
app.use(cors());

const DATA_DIR = path.join(__dirname, "data");
const STATUS_FILE = path.join(DATA_DIR, "status.json");

if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

function defaultStatus() {
  return {
    cameraId: "lot-1",
    timestamp: new Date().toISOString(),
    spots: []
  };
}

function loadStatus() {
  try {
    if (!fs.existsSync(STATUS_FILE)) {
      const initial = defaultStatus();
      fs.writeFileSync(STATUS_FILE, JSON.stringify(initial, null, 2));
      return initial;
    }

    const raw = fs.readFileSync(STATUS_FILE, "utf-8");
    return JSON.parse(raw);
  } catch (err) {
    console.error("Failed to load status.json:", err);
    return defaultStatus();
  }
}

function saveStatus(status) {
  fs.writeFileSync(STATUS_FILE, JSON.stringify(status, null, 2));
}

function normalizeSpot(spot) {
  return {
    id: String(spot.id),
    occupied: Boolean(spot.occupied),
    confidence: Number(spot.confidence ?? 0),
    reservedBy: spot.reservedBy ?? null,
    reservedAt: spot.reservedAt ?? null
  };
}

app.get("/api/status", (req, res) => {
  const status = loadStatus();
  res.json(status);
});

/*
  Detector integration endpoint
  Matches Python --post payload:
  {
    "cameraId": "lot-1",
    "timestamp": "...",
    "spots": [
      {"id":"S1","occupied":true,"confidence":0.87},
      ...
    ]
  }
*/
app.post("/api/spots/update", (req, res) => {
  const incoming = req.body;

  if (!incoming || !Array.isArray(incoming.spots)) {
    return res.status(400).json({ message: "Invalid payload" });
  }

  const current = loadStatus();

  const reservationMap = new Map();
  for (const spot of current.spots || []) {
    reservationMap.set(String(spot.id), {
      reservedBy: spot.reservedBy ?? null,
      reservedAt: spot.reservedAt ?? null
    });
  }

  const merged = {
    cameraId: incoming.cameraId || current.cameraId || "lot-1",
    timestamp: incoming.timestamp || new Date().toISOString(),
    spots: incoming.spots.map((spot) => {
      const previousReservation = reservationMap.get(String(spot.id)) || {
        reservedBy: null,
        reservedAt: null
      };

      return {
        id: String(spot.id),
        occupied: Boolean(spot.occupied),
        confidence: Number(spot.confidence ?? 0),
        reservedBy: previousReservation.reservedBy,
        reservedAt: previousReservation.reservedAt
      };
    })
  };

  saveStatus(merged);
  res.json({ message: "Status updated", spotCount: merged.spots.length });
});

/*
  Reserve a spot from the website.
  Rules:
  - cannot reserve if physically occupied
  - cannot reserve if already reserved
*/
app.post("/api/reserve/:id", (req, res) => {
  const spotId = String(req.params.id);
  const { name } = req.body || {};

  const status = loadStatus();
  const spot = status.spots.find((s) => String(s.id) === spotId);

  if (!spot) {
    return res.status(404).json({ message: "Spot not found" });
  }

  if (spot.occupied) {
    return res.status(400).json({ message: "Spot is currently occupied" });
  }

  if (spot.reservedBy) {
    return res.status(400).json({ message: "Spot is already reserved" });
  }

  spot.reservedBy = name?.trim() || "Guest";
  spot.reservedAt = new Date().toISOString();

  saveStatus(status);
  res.json({ message: `Spot ${spotId} reserved`, spot });
});

/*
  Clear reservation
*/
app.post("/api/release/:id", (req, res) => {
  const spotId = String(req.params.id);

  const status = loadStatus();
  const spot = status.spots.find((s) => String(s.id) === spotId);

  if (!spot) {
    return res.status(404).json({ message: "Spot not found" });
  }

  spot.reservedBy = null;
  spot.reservedAt = null;

  saveStatus(status);
  res.json({ message: `Spot ${spotId} released`, spot });
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`Server running on port ${PORT}`);
});