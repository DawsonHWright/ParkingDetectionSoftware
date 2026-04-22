from datetime import datetime, timezone
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

status_store = {
    "cameraId": "lot-1",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "spots": []
}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify(status_store)

@app.route("/api/spots/update", methods=["POST"])
def update_spots():
    global status_store

    incoming = request.get_json(silent=True)
    if not incoming or not isinstance(incoming.get("spots"), list):
        return jsonify({"message": "Invalid payload"}), 400

    reservation_map = {
        str(spot["id"]): {
            "reservedBy": spot.get("reservedBy"),
            "reservedAt": spot.get("reservedAt")
        }
        for spot in status_store.get("spots", [])
    }

    merged_spots = []
    for spot in incoming["spots"]:
        prev = reservation_map.get(str(spot["id"]), {
            "reservedBy": None,
            "reservedAt": None
        })

        merged_spots.append({
            "id": str(spot["id"]),
            "occupied": bool(spot.get("occupied", False)),
            "confidence": float(spot.get("confidence", 0)),
            "reservedBy": prev["reservedBy"],
            "reservedAt": prev["reservedAt"]
        })

    status_store = {
        "cameraId": incoming.get("cameraId", "lot-1"),
        "timestamp": incoming.get("timestamp", now_iso()),
        "spots": merged_spots
    }

    return jsonify({"message": "Status updated", "spotCount": len(merged_spots)})

@app.route("/api/reserve/<spot_id>", methods=["POST"])
def reserve_spot(spot_id):
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip() or "Guest"

    spot = next((s for s in status_store["spots"] if str(s["id"]) == str(spot_id)), None)

    if not spot:
        return jsonify({"message": "Spot not found"}), 404
    if spot.get("occupied"):
        return jsonify({"message": "Spot is currently occupied"}), 400
    if spot.get("reservedBy"):
        return jsonify({"message": "Spot is already reserved"}), 400

    spot["reservedBy"] = name
    spot["reservedAt"] = now_iso()
    status_store["timestamp"] = now_iso()

    return jsonify({"message": f"Spot {spot_id} reserved", "spot": spot})

@app.route("/api/release/<spot_id>", methods=["POST"])
def release_spot(spot_id):
    spot = next((s for s in status_store["spots"] if str(s["id"]) == str(spot_id)), None)

    if not spot:
        return jsonify({"message": "Spot not found"}), 404

    spot["reservedBy"] = None
    spot["reservedAt"] = None
    status_store["timestamp"] = now_iso()

    return jsonify({"message": f"Spot {spot_id} released", "spot": spot})

if __name__ == "__main__":
    app.run(debug=True, port=5000)