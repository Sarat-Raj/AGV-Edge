"""
Warehouse AGV - Real-time 2D Map Visualizer

Renders a live top-down view of the growing voxel map as a 2D maze/grid.
Shows: walls, robot position, aisle labels, explored area, path trail.

Two modes:
1. Terminal (ASCII) — runs on Jetson, low resource
2. Image output — generates PNG frames for web dashboard
"""

import math
import time
from typing import Optional, Tuple

import numpy as np
import cv2

import config
from odometry import Pose
from semantic_map import SemanticMap
from mapping import VoxelMap


# --- Color Palette (BGR for OpenCV) ---
COLOR_BACKGROUND = (40, 40, 40)       # Dark gray - unknown
COLOR_FREE = (80, 80, 80)             # Medium gray - explored/free
COLOR_WALL = (200, 200, 200)          # Light gray - occupied/wall
COLOR_ROBOT = (0, 200, 0)             # Green - robot
COLOR_ROBOT_HEADING = (0, 255, 100)   # Bright green - heading arrow
COLOR_PATH = (100, 60, 0)             # Dark blue - breadcrumb trail
COLOR_LANDMARK = (0, 100, 255)        # Orange - aisle labels
COLOR_GOAL = (0, 0, 255)              # Red - navigation goal
COLOR_GRID = (50, 50, 50)             # Subtle grid lines


class MapVisualizer:
    """
    Real-time 2D map renderer.
    
    Converts the 3D voxel map into a 2D top-down occupancy grid
    and renders it as an image with overlays.
    """

    def __init__(self, pixels_per_meter: float = 20.0, window_size: Tuple[int, int] = (800, 600)):
        """
        Args:
            pixels_per_meter: Resolution of the rendered map
            window_size: Output image size (width, height)
        """
        self.ppm = pixels_per_meter
        self.width, self.height = window_size

        # Camera/view center (world coordinates)
        self.view_center_x = 0.0
        self.view_center_y = 0.0
        self.follow_robot = True  # Auto-center on robot

        # Rendering state
        self._canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self._last_render_time = 0
        self._render_interval = 0.5  # seconds (2 FPS for map)

    def world_to_pixel(self, wx: float, wy: float) -> Tuple[int, int]:
        """Convert world coordinates to pixel coordinates on canvas."""
        # Center of canvas = view_center
        px = int(self.width / 2 + (wx - self.view_center_x) * self.ppm)
        py = int(self.height / 2 - (wy - self.view_center_y) * self.ppm)  # Y flipped
        return px, py

    def pixel_to_world(self, px: int, py: int) -> Tuple[float, float]:
        """Convert pixel coordinates to world coordinates."""
        wx = self.view_center_x + (px - self.width / 2) / self.ppm
        wy = self.view_center_y - (py - self.height / 2) / self.ppm
        return wx, wy

    def should_render(self) -> bool:
        """Check if enough time has passed for next render."""
        return time.time() - self._last_render_time >= self._render_interval

    def render(self, voxel_map: VoxelMap, robot_pose: Pose,
               semantic_map: SemanticMap, goal: Optional[str] = None) -> np.ndarray:
        """
        Render the current map state to an image.
        
        Args:
            voxel_map: Current voxel map
            robot_pose: Current robot pose
            semantic_map: Semantic map with landmarks
            goal: Optional current navigation goal label
            
        Returns:
            BGR image (numpy array) of the rendered map
        """
        self._last_render_time = time.time()

        # Follow robot
        if self.follow_robot:
            self.view_center_x = robot_pose.x
            self.view_center_y = robot_pose.y

        # Clear canvas
        self._canvas[:] = COLOR_BACKGROUND

        # 1. Render occupancy grid
        self._render_occupancy(voxel_map)

        # 2. Render exploration path
        self._render_path(semantic_map)

        # 3. Render landmarks
        self._render_landmarks(semantic_map, goal)

        # 4. Render robot
        self._render_robot(robot_pose)

        # 5. Render HUD (stats overlay)
        self._render_hud(voxel_map, robot_pose, semantic_map, goal)

        return self._canvas.copy()

    def _render_occupancy(self, voxel_map: VoxelMap):
        """Render 2D occupancy grid from voxel map."""
        occupancy = voxel_map.get_2d_occupancy(z_min=0.1, z_max=1.5)

        # Draw free cells
        for (vx, vy) in occupancy["free"]:
            wx = (vx + 0.5) * voxel_map.resolution
            wy = (vy + 0.5) * voxel_map.resolution
            px, py = self.world_to_pixel(wx, wy)

            if 0 <= px < self.width and 0 <= py < self.height:
                # Draw a small square for each voxel
                size = max(1, int(voxel_map.resolution * self.ppm))
                cv2.rectangle(self._canvas,
                              (px - size // 2, py - size // 2),
                              (px + size // 2, py + size // 2),
                              COLOR_FREE, -1)

        # Draw occupied cells (walls)
        for (vx, vy) in occupancy["occupied"]:
            wx = (vx + 0.5) * voxel_map.resolution
            wy = (vy + 0.5) * voxel_map.resolution
            px, py = self.world_to_pixel(wx, wy)

            if 0 <= px < self.width and 0 <= py < self.height:
                size = max(1, int(voxel_map.resolution * self.ppm))
                cv2.rectangle(self._canvas,
                              (px - size // 2, py - size // 2),
                              (px + size // 2, py + size // 2),
                              COLOR_WALL, -1)

    def _render_path(self, semantic_map: SemanticMap):
        """Render breadcrumb trail."""
        path = semantic_map.exploration_path
        if len(path) < 2:
            return

        for i in range(1, len(path)):
            p1 = self.world_to_pixel(path[i - 1][0], path[i - 1][1])
            p2 = self.world_to_pixel(path[i][0], path[i][1])

            # Only draw if on screen
            if (0 <= p1[0] < self.width and 0 <= p1[1] < self.height) or \
               (0 <= p2[0] < self.width and 0 <= p2[1] < self.height):
                cv2.line(self._canvas, p1, p2, COLOR_PATH, 1, cv2.LINE_AA)

    def _render_landmarks(self, semantic_map: SemanticMap, goal: Optional[str]):
        """Render aisle label landmarks."""
        for label, lm in semantic_map.landmarks.items():
            px, py = self.world_to_pixel(lm.x, lm.y)

            if 0 <= px < self.width and 0 <= py < self.height:
                # Choose color based on whether this is the goal
                color = COLOR_GOAL if (goal and label == goal) else COLOR_LANDMARK

                # Draw marker
                cv2.circle(self._canvas, (px, py), 8, color, -1)
                cv2.circle(self._canvas, (px, py), 10, color, 2)

                # Draw label text
                text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                text_x = px - text_size[0] // 2
                text_y = py - 15

                # Background for readability
                cv2.rectangle(self._canvas,
                              (text_x - 2, text_y - text_size[1] - 2),
                              (text_x + text_size[0] + 2, text_y + 4),
                              (0, 0, 0), -1)
                cv2.putText(self._canvas, label,
                            (text_x, text_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    def _render_robot(self, pose: Pose):
        """Render robot position and heading."""
        px, py = self.world_to_pixel(pose.x, pose.y)

        # Robot body (circle)
        robot_radius = max(5, int(0.10 * self.ppm))  # 10cm radius
        cv2.circle(self._canvas, (px, py), robot_radius, COLOR_ROBOT, -1)

        # Heading arrow
        arrow_length = robot_radius * 2.5
        end_x = int(px + arrow_length * math.cos(-pose.theta + math.pi / 2))
        end_y = int(py + arrow_length * math.sin(-pose.theta + math.pi / 2))
        # Adjust for flipped Y: heading in world → screen
        end_x = int(px + arrow_length * math.cos(pose.theta))
        end_y = int(py - arrow_length * math.sin(pose.theta))

        cv2.arrowedLine(self._canvas, (px, py), (end_x, end_y),
                        COLOR_ROBOT_HEADING, 2, tipLength=0.4)

    def _render_hud(self, voxel_map: VoxelMap, pose: Pose,
                    semantic_map: SemanticMap, goal: Optional[str]):
        """Render heads-up display with stats."""
        lines = [
            f"Pos: ({pose.x:.1f}, {pose.y:.1f}) Hdg: {math.degrees(pose.theta):.0f}deg",
            f"Voxels: {voxel_map.num_voxels} ({voxel_map.memory_estimate_kb:.0f}KB)",
            f"Landmarks: {len(semantic_map.landmarks)}",
        ]
        if goal:
            lines.append(f"GOAL: {goal}")

        # Draw semi-transparent background
        hud_height = 20 * len(lines) + 10
        overlay = self._canvas.copy()
        cv2.rectangle(overlay, (5, 5), (300, hud_height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, self._canvas, 0.4, 0, self._canvas)

        # Draw text
        for i, line in enumerate(lines):
            cv2.putText(self._canvas, line,
                        (10, 22 + i * 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    def save_frame(self, filepath: str = "map_frame.png"):
        """Save current canvas to file."""
        cv2.imwrite(filepath, self._canvas)


class TerminalMapVisualizer:
    """
    ASCII-based map visualizer for terminal display.
    Lightweight, runs directly on Jetson Nano.
    Uses only pure ASCII characters (no Unicode).
    """

    CHARS = {
        'unknown': ' ',
        'free': '.',
        'wall': '#',
        'robot': 'R',
        'path': ',',
        'landmark': '*',
        'goal': '!',
    }

    def __init__(self, width: int = 60, height: int = 30, meters_per_char: float = 0.25):
        self.width = width
        self.height = height
        self.mpc = meters_per_char  # World meters per character cell

    def render(self, voxel_map: VoxelMap, robot_pose: Pose,
               semantic_map: SemanticMap, goal: Optional[str] = None) -> str:
        """
        Render map as ASCII string.
        
        Returns:
            Multi-line string ready to print
        """
        # Initialize grid
        grid = [[self.CHARS['unknown']] * self.width for _ in range(self.height)]

        # Center on robot
        cx = robot_pose.x
        cy = robot_pose.y

        # Get 2D occupancy
        occupancy = voxel_map.get_2d_occupancy(z_min=0.1, z_max=1.5)

        # Render free cells
        for (vx, vy) in occupancy["free"]:
            wx = (vx + 0.5) * voxel_map.resolution
            wy = (vy + 0.5) * voxel_map.resolution
            col = int((wx - cx) / self.mpc + self.width / 2)
            row = int(-(wy - cy) / self.mpc + self.height / 2)
            if 0 <= row < self.height and 0 <= col < self.width:
                grid[row][col] = self.CHARS['free']

        # Render walls
        for (vx, vy) in occupancy["occupied"]:
            wx = (vx + 0.5) * voxel_map.resolution
            wy = (vy + 0.5) * voxel_map.resolution
            col = int((wx - cx) / self.mpc + self.width / 2)
            row = int(-(wy - cy) / self.mpc + self.height / 2)
            if 0 <= row < self.height and 0 <= col < self.width:
                grid[row][col] = self.CHARS['wall']

        # Render landmarks
        for label, lm in semantic_map.landmarks.items():
            col = int((lm.x - cx) / self.mpc + self.width / 2)
            row = int(-(lm.y - cy) / self.mpc + self.height / 2)
            if 0 <= row < self.height and 0 <= col < self.width:
                char = self.CHARS['goal'] if (goal and label == goal) else self.CHARS['landmark']
                grid[row][col] = char
                # Place label text next to marker
                for i, c in enumerate(label):
                    tc = col + 1 + i
                    if 0 <= tc < self.width:
                        grid[row][tc] = c

        # Render robot (always at center)
        robot_col = self.width // 2
        robot_row = self.height // 2
        grid[robot_row][robot_col] = self.CHARS['robot']

        # Heading indicator
        hdg_chars = {0: '>', 1: '/', 2: '^', 3: '\\', 4: '<', 5: '/', 6: 'v', 7: '\\'}
        hdg_idx = int((robot_pose.theta + math.pi / 8) / (math.pi / 4)) % 8
        hdg_char = hdg_chars.get(hdg_idx, '>')
        # Place heading arrow in front of robot
        dx = int(round(math.cos(robot_pose.theta)))
        dy = int(round(math.sin(robot_pose.theta)))
        hcol = robot_col + dx
        hrow = robot_row - dy
        if 0 <= hrow < self.height and 0 <= hcol < self.width:
            grid[hrow][hcol] = hdg_char

        # Build output string
        border = '+' + '-' * self.width + '+'
        bottom = '+' + '-' * self.width + '+'

        lines = [border]
        for row in grid:
            lines.append('|' + ''.join(row) + '|')
        lines.append(bottom)

        # Stats line
        lines.append(f" Pos:({robot_pose.x:.1f},{robot_pose.y:.1f}) "
                     f"Hdg:{math.degrees(robot_pose.theta):.0f}° "
                     f"Voxels:{voxel_map.num_voxels} "
                     f"Signs:{len(semantic_map.landmarks)}"
                     + (f" GOAL:{goal}" if goal else ""))

        return '\n'.join(lines)

    def print_map(self, voxel_map: VoxelMap, robot_pose: Pose,
                  semantic_map: SemanticMap, goal: Optional[str] = None):
        """Render and print to terminal (with clear screen)."""
        # ANSI escape to move cursor to top-left (no flicker)
        print('\033[H\033[J', end='')
        print(self.render(voxel_map, robot_pose, semantic_map, goal))


# --- Quick Demo ---
if __name__ == "__main__":
    # Create a simulated map with walls
    vmap = VoxelMap(resolution=0.1)
    smap = SemanticMap()

    # Simulate corridor walls
    for x in np.arange(-2, 10, 0.1):
        # Left wall
        vmap.grid[vmap._world_to_voxel(x, 1.5, 0.5)] = type('Cell', (), {'occupied': True, 'log_odds': 1.0})()
        # Right wall
        vmap.grid[vmap._world_to_voxel(x, -1.5, 0.5)] = type('Cell', (), {'occupied': True, 'log_odds': 1.0})()

    # Add some free space in between
    for x in np.arange(-1, 9, 0.2):
        for y in np.arange(-1.3, 1.3, 0.2):
            key = vmap._world_to_voxel(x, y, 0.5)
            if key not in vmap.grid:
                vmap.grid[key] = type('Cell', (), {'occupied': False, 'log_odds': -0.5})()

    # Add landmarks
    smap.add_landmark("H2", Pose(0.0, 0.0, 0.0), 0.9)
    smap.add_landmark("H3", Pose(3.0, 0.0, 0.0), 0.9)
    smap.add_landmark("H4", Pose(6.0, 0.0, 0.0), 0.9)

    robot = Pose(1.5, 0.0, 0.0)

    # Terminal view
    term_viz = TerminalMapVisualizer(width=60, height=20)
    print(term_viz.render(vmap, robot, smap, goal="H4"))

    # Image view
    img_viz = MapVisualizer(pixels_per_meter=30, window_size=(800, 400))
    frame = img_viz.render(vmap, robot, smap, goal="H4")
    img_viz.save_frame("/tmp/agv_map_demo.png")
    print(f"\nImage saved to /tmp/agv_map_demo.png ({frame.shape[1]}x{frame.shape[0]})")
