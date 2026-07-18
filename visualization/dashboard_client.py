"""
Warehouse AGV - Dashboard Client

Runs on the Jetson Nano alongside the main control loop.
Periodically sends map state to the web dashboard server.
"""

import time
import threading
from typing import Optional

import requests

import config
from odometry import Pose
from mapping import VoxelMap
from semantic_map import SemanticMap


class DashboardClient:
    """Sends map state updates to the web dashboard."""

    def __init__(self, dashboard_url: str = f"http://{config.PLANNER_HOST}:8080"):
        self.url = f"{dashboard_url}/update"
        self.update_interval = 0.5  # seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # References to shared state (set by main loop)
        self.voxel_map: Optional[VoxelMap] = None
        self.semantic_map: Optional[SemanticMap] = None
        self.pose: Optional[Pose] = None
        self.goal: Optional[str] = None

    def start(self, voxel_map: VoxelMap, semantic_map: SemanticMap):
        """Start background update thread."""
        self.voxel_map = voxel_map
        self.semantic_map = semantic_map
        self._running = True
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        print(f"[Dashboard] Streaming to {self.url}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def update_pose(self, pose: Pose, goal: Optional[str] = None):
        """Update current robot pose (called from main loop)."""
        self.pose = pose
        self.goal = goal

    def _update_loop(self):
        """Background loop that pushes state to dashboard."""
        while self._running:
            try:
                self._send_update()
            except Exception as e:
                pass  # Silent fail — dashboard is optional
            time.sleep(self.update_interval)

    def _send_update(self):
        """Build and send state payload."""
        if not self.voxel_map or not self.pose:
            return

        # Get 2D occupancy
        occupancy = self.voxel_map.get_2d_occupancy(z_min=0.1, z_max=1.5)

        # Limit data sent (only nearby voxels to keep payload small)
        max_cells = 2000
        walls = list(occupancy["occupied"])[:max_cells]
        free = list(occupancy["free"])[:max_cells]

        # Build payload
        payload = {
            "robot": {
                "x": self.pose.x,
                "y": self.pose.y,
                "theta": self.pose.theta
            },
            "landmarks": {
                label: {"x": lm.x, "y": lm.y, "label": lm.label}
                for label, lm in self.semantic_map.landmarks.items()
            },
            "walls": [[vx, vy] for vx, vy in walls],
            "free": [[vx, vy] for vx, vy in free],
            "path": self.semantic_map.exploration_path[-100:],
            "goal": self.goal,
            "resolution": self.voxel_map.resolution,
            "stats": self.voxel_map.get_stats()
        }

        requests.post(self.url, json=payload, timeout=2)
