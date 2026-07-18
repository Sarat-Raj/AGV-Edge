"""
Warehouse AGV - Web Dashboard Server

Lightweight web server that runs alongside the planner on the MacBook.
Streams the live 2D map to a browser via WebSocket.

The Jetson sends map state updates, and the browser renders them.

Run: python dashboard.py
Open: http://localhost:8080
"""

import asyncio
import json
import time
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="AGV Dashboard")

# Shared state - updated by Jetson's HTTP posts
current_state = {
    "robot": {"x": 0, "y": 0, "theta": 0},
    "landmarks": {},
    "walls": [],
    "free": [],
    "path": [],
    "goal": None,
    "stats": {},
    "timestamp": 0
}

# Connected WebSocket clients
clients = set()

DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Warehouse AGV - Live Map</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #1a1a1a; color: #eee; font-family: 'Courier New', monospace; }
        #header { padding: 10px 20px; background: #222; border-bottom: 1px solid #444; display: flex; justify-content: space-between; align-items: center; }
        #header h1 { font-size: 18px; color: #0f0; }
        #stats { font-size: 12px; color: #888; }
        #canvas-container { display: flex; justify-content: center; padding: 20px; }
        canvas { border: 1px solid #333; background: #111; }
        #legend { padding: 10px 20px; display: flex; gap: 20px; font-size: 12px; }
        .legend-item { display: flex; align-items: center; gap: 5px; }
        .legend-color { width: 12px; height: 12px; border-radius: 2px; }
        #status { position: fixed; bottom: 10px; right: 10px; font-size: 11px; padding: 5px 10px; border-radius: 3px; }
        .connected { background: #0a3; color: white; }
        .disconnected { background: #a00; color: white; }
    </style>
</head>
<body>
    <div id="header">
        <h1>🤖 Warehouse AGV — Live Map</h1>
        <div id="stats">Waiting for data...</div>
    </div>
    <div id="legend">
        <div class="legend-item"><div class="legend-color" style="background:#ccc"></div> Wall</div>
        <div class="legend-item"><div class="legend-color" style="background:#555"></div> Free</div>
        <div class="legend-item"><div class="legend-color" style="background:#0c0"></div> Robot</div>
        <div class="legend-item"><div class="legend-color" style="background:#f80"></div> Aisle Sign</div>
        <div class="legend-item"><div class="legend-color" style="background:#f00"></div> Goal</div>
        <div class="legend-item"><div class="legend-color" style="background:#046"></div> Path</div>
    </div>
    <div id="canvas-container">
        <canvas id="map" width="900" height="500"></canvas>
    </div>
    <div id="status" class="disconnected">Disconnected</div>

    <script>
        const canvas = document.getElementById('map');
        const ctx = canvas.getContext('2d');
        const statsEl = document.getElementById('stats');
        const statusEl = document.getElementById('status');

        // View settings
        const PPM = 25; // pixels per meter
        let viewCenterX = 0;
        let viewCenterY = 0;

        function worldToPixel(wx, wy) {
            const px = canvas.width / 2 + (wx - viewCenterX) * PPM;
            const py = canvas.height / 2 - (wy - viewCenterY) * PPM;
            return [px, py];
        }

        function render(state) {
            // Follow robot
            viewCenterX = state.robot.x;
            viewCenterY = state.robot.y;

            // Clear
            ctx.fillStyle = '#1a1a1a';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // Draw grid
            ctx.strokeStyle = '#222';
            ctx.lineWidth = 0.5;
            for (let x = -20; x < 20; x++) {
                const [px] = worldToPixel(x, 0);
                ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, canvas.height); ctx.stroke();
            }
            for (let y = -20; y < 20; y++) {
                const [, py] = worldToPixel(0, y);
                ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(canvas.width, py); ctx.stroke();
            }

            // Draw free space
            const cellSize = Math.max(2, state.resolution * PPM);
            ctx.fillStyle = '#3a3a3a';
            for (const [vx, vy] of state.free || []) {
                const wx = (vx + 0.5) * state.resolution;
                const wy = (vy + 0.5) * state.resolution;
                const [px, py] = worldToPixel(wx, wy);
                ctx.fillRect(px - cellSize/2, py - cellSize/2, cellSize, cellSize);
            }

            // Draw walls
            ctx.fillStyle = '#cccccc';
            for (const [vx, vy] of state.walls || []) {
                const wx = (vx + 0.5) * state.resolution;
                const wy = (vy + 0.5) * state.resolution;
                const [px, py] = worldToPixel(wx, wy);
                ctx.fillRect(px - cellSize/2, py - cellSize/2, cellSize, cellSize);
            }

            // Draw path
            if (state.path && state.path.length > 1) {
                ctx.strokeStyle = '#004466';
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                const [sx, sy] = worldToPixel(state.path[0][0], state.path[0][1]);
                ctx.moveTo(sx, sy);
                for (let i = 1; i < state.path.length; i++) {
                    const [px, py] = worldToPixel(state.path[i][0], state.path[i][1]);
                    ctx.lineTo(px, py);
                }
                ctx.stroke();
            }

            // Draw landmarks
            for (const [label, lm] of Object.entries(state.landmarks || {})) {
                const [px, py] = worldToPixel(lm.x, lm.y);
                const isGoal = state.goal && label === state.goal;
                const color = isGoal ? '#ff0000' : '#ff8800';

                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(px, py, 7, 0, Math.PI * 2);
                ctx.fill();

                ctx.strokeStyle = color;
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(px, py, 10, 0, Math.PI * 2);
                ctx.stroke();

                ctx.fillStyle = color;
                ctx.font = 'bold 14px monospace';
                ctx.textAlign = 'center';
                ctx.fillText(label, px, py - 15);
            }

            // Draw robot
            const [rx, ry] = worldToPixel(state.robot.x, state.robot.y);
            const robotRadius = 8;

            // Body
            ctx.fillStyle = '#00cc00';
            ctx.beginPath();
            ctx.arc(rx, ry, robotRadius, 0, Math.PI * 2);
            ctx.fill();

            // Heading arrow
            const arrowLen = 20;
            const endX = rx + arrowLen * Math.cos(state.robot.theta);
            const endY = ry - arrowLen * Math.sin(state.robot.theta);
            ctx.strokeStyle = '#00ff66';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(rx, ry);
            ctx.lineTo(endX, endY);
            ctx.stroke();

            // Arrowhead
            const angle = Math.atan2(ry - endY, endX - rx);
            ctx.fillStyle = '#00ff66';
            ctx.beginPath();
            ctx.moveTo(endX, endY);
            ctx.lineTo(endX - 8*Math.cos(angle - 0.4), endY + 8*Math.sin(angle - 0.4));
            ctx.lineTo(endX - 8*Math.cos(angle + 0.4), endY + 8*Math.sin(angle + 0.4));
            ctx.fill();

            // Update stats
            const stats = state.stats || {};
            statsEl.textContent = 
                `Pos: (${state.robot.x.toFixed(1)}, ${state.robot.y.toFixed(1)}) | ` +
                `Heading: ${(state.robot.theta * 180 / Math.PI).toFixed(0)}° | ` +
                `Voxels: ${stats.total_voxels || 0} | ` +
                `Signs: ${Object.keys(state.landmarks || {}).length}` +
                (state.goal ? ` | GOAL: ${state.goal}` : '');
        }

        // WebSocket connection
        function connect() {
            const ws = new WebSocket(`ws://${window.location.host}/ws`);

            ws.onopen = () => {
                statusEl.textContent = 'Connected';
                statusEl.className = 'connected';
            };

            ws.onmessage = (event) => {
                try {
                    const state = JSON.parse(event.data);
                    render(state);
                } catch (e) {
                    console.error('Parse error:', e);
                }
            };

            ws.onclose = () => {
                statusEl.textContent = 'Disconnected';
                statusEl.className = 'disconnected';
                setTimeout(connect, 2000); // Reconnect
            };

            ws.onerror = () => ws.close();
        }

        connect();
    </script>
</body>
</html>"""


@app.get("/")
async def get_dashboard():
    return HTMLResponse(DASHBOARD_HTML)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        while True:
            # Send current state periodically
            await websocket.send_json(current_state)
            await asyncio.sleep(0.5)  # 2 FPS updates
    except WebSocketDisconnect:
        clients.discard(websocket)


@app.post("/update")
async def update_state(state: dict):
    """
    Called by the Jetson to push map state updates.
    
    Expected payload:
    {
        "robot": {"x": 1.0, "y": 0.5, "theta": 0.3},
        "landmarks": {"H4": {"x": 6.0, "y": 0.0}},
        "walls": [[vx, vy], ...],
        "free": [[vx, vy], ...],
        "path": [[x, y], ...],
        "goal": "H4",
        "resolution": 0.05,
        "stats": {"total_voxels": 1234}
    }
    """
    global current_state
    current_state = state
    current_state["timestamp"] = time.time()
    return {"status": "ok"}


if __name__ == "__main__":
    print("=" * 50)
    print("  AGV Dashboard — http://localhost:8080")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8080)
