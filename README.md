# Parking Detection Software

Parking Detection Software is a parking lot monitoring and reservation prototype. The project connects a parking dashboard, a backend API, and computer vision code to show which parking spaces are open, occupied, or reserved.

The current deployed demo is on the `pages-demo` branch. The frontend files are stored in the `docs/` folder so the project can be deployed through GitHub Pages.

## Project Purpose

The purpose of this project is to create a software prototype that helps users view parking availability and reserve open parking spaces.

The project focuses on three main ideas:

1. Detect parking spot status using computer vision.
2. Send parking spot data to a backend API.
3. Display live parking information on a web dashboard.

This project is a prototype. It shows the main idea and software flow, but it is not a finished production parking system.

## Current Features

1. Web dashboard for parking availability
2. Live parking map with a reservation system
3. Auto-generated parking lot layout based on returned spot IDs
4. Summary cards for total, free, occupied, and reserved spots
5. Color-coded spot status:
   1. Green means open
   2. Yellow means selected
   3. Red means unavailable, occupied, or reserved
6. User can select an open parking spot before reserving it
7. User can enter a name to reserve a selected spot
8. Frontend refreshes parking status automatically
9. Backend API supports parking status updates
10. Backend API supports reserving and releasing spots
11. Computer vision detector can analyze parking spots from image, folder, video, webcam, or stream input
12. Detector can output JSON and optionally post updates to the backend

## Deployed Demo

The deployed frontend is handled through GitHub Pages.

To view the demo:

1. Go to the repository on GitHub.
2. Open the `pages-demo` branch.
3. Click the active deployment link shown by GitHub.
4. The GitHub Pages site will open the parking dashboard from the `docs/` folder.

No terminal commands are needed to view the deployed demo.

## Repository Branch

The main deployment work is on:

```text
pages-demo
```

This branch contains the GitHub Pages demo files, backend code, legacy web code, and computer vision code.

## Project Structure

```text
ParkingDetectionSoftware/
├── docs/
│   ├── index.html
│   ├── app.js
│   └── style.css
│
├── parking-backend/
│   ├── app.py
│   └── requirements.txt
│
├── parking-web-old/
│   ├── server.js
│   ├── package.json
│   └── data/
│
├── parking_cameraVision/
│   ├── detector.py
│   ├── mask_generator.py
│   ├── run_detector.sh
│   ├── requirements.txt
│   ├── inputs/
│   └── outputs/
│
├── LICENSE
└── README.md
```

## Frontend

The active frontend is located in:

```text
docs/
```

Important frontend files:

| File | Purpose |
|---|---|
| `docs/index.html` | Main dashboard page |
| `docs/app.js` | Frontend logic, API calls, parking layout generation, and reservation behavior |
| `docs/style.css` | Dashboard styling and parking lot map visuals |

The frontend displays:

1. Camera ID
2. Last update time
3. Selected parking spot
4. Total spots
5. Free spots
6. Occupied spots
7. Reserved spots
8. Parking lot map
9. Reservation controls

The frontend currently connects to the deployed backend using the API base URL inside `docs/app.js`.

```js
const API_BASE = "https://parkingdetectionsoftware.onrender.com";
```

## Backend

The active backend is located in:

```text
parking-backend/
```

The backend is written with Flask. It receives parking spot updates, stores the current parking status, and allows the frontend to reserve or release parking spots.

Main backend responsibilities:

1. Return current parking lot status
2. Receive updated parking spot data from the detector
3. Preserve reservation information when new detector data is received
4. Allow a user to reserve an open spot
5. Allow a spot reservation to be released

Main API routes:

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/status` | Returns the current parking lot status |
| `POST` | `/api/spots/update` | Receives updated parking data from the detector |
| `POST` | `/api/reserve/<spot_id>` | Reserves an available parking spot |
| `POST` | `/api/release/<spot_id>` | Releases a reserved parking spot |

The backend currently stores status in memory. This is fine for a prototype, but it means the data may reset when the backend restarts. A future version should use a persistent database.

## Computer Vision

The computer vision code is located in:

```text
parking_cameraVision/
```

Important computer vision files:

| File | Purpose |
|---|---|
| `detector.py` | Detects whether parking spots are occupied or free |
| `mask_generator.py` | Helps create parking spot masks |
| `run_detector.sh` | Example script for running the detector |
| `requirements.txt` | Python dependencies for computer vision |

The detector supports:

1. Image input
2. Folder input
3. Video input
4. Webcam input
5. URL or stream input

The detector uses a saved mask to identify parking spot regions. It then analyzes those regions and creates a JSON payload with the spot status.

Example JSON format:

```json
{
  "cameraId": "lot-1",
  "timestamp": "2026-04-29T12:00:00",
  "spots": [
    {
      "id": "S1",
      "occupied": false,
      "confidence": 0.87
    }
  ]
}
```

## Legacy Web Version

The `parking-web-old/` folder contains an earlier Node and Express version of the web/backend system.

This folder is kept for reference, but the current demo uses:

```text
docs/
parking-backend/
parking_cameraVision/
```

The current deployed frontend is the GitHub Pages version inside `docs/`.

## How the System Works

The intended project flow is:

1. The detector analyzes parking spaces from a camera, image, video, folder, or stream.
2. The detector creates a JSON payload with parking spot data.
3. The backend receives the updated spot data through `/api/spots/update`.
4. The frontend requests the latest status from `/api/status`.
5. The dashboard displays each parking spot as open, occupied, selected, or reserved.
6. A user can select an open spot and reserve it.
7. The backend stores the reservation information with the parking spot status.

## Tools and Technologies

| Area | Tools |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, Flask, Flask-CORS, Render |
| Computer Vision | OpenCV, NumPy, Requests |
| Legacy Backend | Node.js, Express |
| Deployment | GitHub Pages for the frontend, Render backend URL in the frontend code |
| Version Control | Git and GitHub |

## Individual Contributions

These contributions are based on the visible GitHub commit history, the current project structure, and our team work during the project.

| Contributor | Contributions |
|---|---|
| DawsonHWright | Created the repository and early project file structure. Worked on documentation files, website updates, cloud and backend trials, the Flask backend, backend connection testing, detector worker work, and hosting/deployment connection work. |
| Dj-messup | Worked on the deployed GitHub Pages demo branch. Added the GitHub Pages demo site, moved the GitHub Pages files into the `docs/` folder, updated the frontend to match requested design changes, worked on deployment fixes, added the auto-generated parking lot layout for the frontend dashboard, researched backend deployment options, tested Flask and Render demos, and helped reorganize the connection between the frontend, backend, and camera/detector output. |
| cameronhock | Worked heavily on the camera and computer vision side of the project. Added the parking camera vision folder, worked on OpenCV camera and detection files, helped with camera input and parking spot detection, contributed camera updates, and researched YOLO and SAM to determine whether full automation could be implemented in a future version. |
| Tom Bennett / Client Innovation Center | Provided project direction and design feedback for the parking dashboard and expected user experience. This is listed as project input rather than a code contribution. |

## What Was Implemented

The current project includes:

1. A deployed frontend dashboard through GitHub Pages
2. A Flask backend API
3. A detector that can generate parking spot status data
4. A parking reservation interface
5. Basic frontend and backend integration
6. A simple auto-generated parking map
7. Computer vision code using OpenCV and masks

## What Was Not Fully Implemented

The following ideas were discussed or planned but are not fully implemented in the current version:

1. Fully automated real parking lot camera integration
2. A finalized real-world parking lot map for each lot
3. Persistent database storage for long-term reservations
4. User accounts or authentication
5. YOLO-based vehicle detection
6. SAM-based segmentation
7. Fully automated parking spot detection from side-view cameras
8. A production-ready deployment pipeline

## Known Limitations

This project is still a prototype. Known limitations include:

1. The backend currently stores data in memory.
2. Parking reservations may reset if the backend restarts.
3. The parking lot layout is generated automatically instead of using a final custom map.
4. The computer vision system depends on masks and image conditions.
5. Detection accuracy may change depending on lighting, camera angle, and image quality.
6. The frontend depends on the deployed backend URL being available.
7. There is no login system, so reservations are based only on the entered name.

## Future Work

If we had more time, we would improve the project by:

1. Connecting the system to actual parking lot cameras
2. Creating a more accurate map for each parking lot
3. Improving side-view camera detection
4. Testing the system with real parking lot footage
5. Adding a persistent database
6. Adding user authentication
7. Adding automatic reservation expiration
8. Improving error handling on the frontend
9. Deploying the backend with a more stable production setup
10. Exploring YOLO for vehicle detection
11. Exploring SAM for parking space or vehicle segmentation

## License

This project uses the MIT License.