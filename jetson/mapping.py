"""
Warehouse AGV - OctoMap Voxel Grid Manager

Builds a sparse 3D voxel map from RealSense depth data.
Uses OctoMap for memory-efficient 3D occupancy representation.

Note: This module provides a simplified Python wrapper.
For production use on Jetson Nano, consider using the C++ OctoMap library
directly via octomap_server ROS node or pybind11 bindings.
"""

import time
import math
import struct
import numpy as np
from typing import Optional, Tuple

import config
from odometry import Pose


class VoxelCell:
    """A single voxel cell in the occupancy grid."""
    __slots__ = ['occupied', 'log_odds']

    def __init__(self):
        self.occupied = False
        self.log_odds = 0.0  # Log-odds occupancy probability

    def update(self, occupied: bool):
        """Update cell with Bayesian log-odds."""
        if occupied:
            self.log_odds += 0.85  # hit
        else:
            self.log_odds -= 0.4  # miss

        # Clamp
        self.log_odds = max(-2.0, min(3.5, self.log_odds))
        self.occupied = self.log_odds > 0


class VoxelMap:
    """
    Lightweight sparse 3D voxel grid using a dictionary.
    
    This is a simplified version of OctoMap that runs in pure Python.
    For better performance on Jetson Nano, use the C++ octomap library.
    
    Coordinate system:
    - x: forward (robot heading direction)
    - y: left
    - z: up
    """

    def __init__(self, resolution: float = config.OCTOMAP_RESOLUTION):
        self.resolution = resolution
        self.grid = {}  # Dict[Tuple[int,int,int], VoxelCell]
        self.max_range = config.OCTOMAP_MAX_RANGE

        # Statistics
        self.total_insertions = 0
        self.last_save_time = time.time()

    def _world_to_voxel(self, x: float, y: float, z: float) -> Tuple[int, int, int]:
        """Convert world coordinates to voxel indices."""
        return (
            int(math.floor(x / self.resolution)),
            int(math.floor(y / self.resolution)),
            int(math.floor(z / self.resolution))
        )

    def _voxel_to_world(self, vx: int, vy: int, vz: int) -> Tuple[float, float, float]:
        """Convert voxel indices to world coordinate centers."""
        return (
            (vx + 0.5) * self.resolution,
            (vy + 0.5) * self.resolution,
            (vz + 0.5) * self.resolution
        )

    def insert_point_cloud(self, points: np.ndarray, robot_pose: Pose,
                           sensor_height: float = 0.15):
        """
        Insert a point cloud into the voxel grid.
        
        Args:
            points: Nx3 array of points in camera frame (x=right, y=down, z=forward)
            robot_pose: Current robot pose in world frame
            sensor_height: Height of the sensor above ground (meters)
        """
        if len(points) == 0:
            return

        # Transform points from camera frame to world frame
        # Camera: x=right, y=down, z=forward
        # World: x=forward, y=left, z=up
        cos_theta = math.cos(robot_pose.theta)
        sin_theta = math.sin(robot_pose.theta)

        # Subsample for performance (process every Nth point)
        step = max(1, len(points) // 2000)  # Max ~2000 points per insertion
        sampled = points[::step]

        sensor_origin = np.array([robot_pose.x, robot_pose.y, sensor_height])

        for pt in sampled:
            # Camera to robot frame transformation
            # cam_z -> robot_x (forward), cam_x -> robot_y (right), cam_y -> robot_z (down)
            rx = pt[2]   # forward = cam_z
            ry = -pt[0]  # left = -cam_x
            rz = -pt[1]  # up = -cam_y

            # Robot frame to world frame (rotate by heading)
            wx = robot_pose.x + rx * cos_theta - ry * sin_theta
            wy = robot_pose.y + rx * sin_theta + ry * cos_theta
            wz = sensor_height + rz

            # Range check
            dist = math.sqrt((wx - robot_pose.x) ** 2 + (wy - robot_pose.y) ** 2)
            if dist > self.max_range:
                continue

            # Mark the endpoint as occupied
            voxel_key = self._world_to_voxel(wx, wy, wz)
            if voxel_key not in self.grid:
                self.grid[voxel_key] = VoxelCell()
            self.grid[voxel_key].update(occupied=True)

        self.total_insertions += 1

        # Ray casting for free space (simplified - just mark sensor origin area)
        origin_key = self._world_to_voxel(robot_pose.x, robot_pose.y, sensor_height)
        if origin_key not in self.grid:
            self.grid[origin_key] = VoxelCell()
        self.grid[origin_key].update(occupied=False)

    def is_occupied(self, x: float, y: float, z: float) -> bool:
        """Check if a world position is occupied."""
        key = self._world_to_voxel(x, y, z)
        cell = self.grid.get(key)
        return cell.occupied if cell else False

    def is_free(self, x: float, y: float, z: float) -> bool:
        """Check if a world position is known free (not unknown)."""
        key = self._world_to_voxel(x, y, z)
        cell = self.grid.get(key)
        if cell is None:
            return False  # Unknown, not free
        return not cell.occupied

    def get_2d_occupancy(self, z_min: float = 0.1, z_max: float = 1.5) -> dict:
        """
        Project 3D voxels onto a 2D occupancy grid (top-down view).
        Considers voxels between z_min and z_max as obstacles.
        
        Returns:
            Dict with 'occupied' and 'free' sets of (vx, vy) tuples
        """
        occupied_2d = set()
        free_2d = set()

        for (vx, vy, vz), cell in self.grid.items():
            wz = (vz + 0.5) * self.resolution
            if z_min <= wz <= z_max:
                key_2d = (vx, vy)
                if cell.occupied:
                    occupied_2d.add(key_2d)
                else:
                    free_2d.add(key_2d)

        # Occupied takes priority over free
        free_2d -= occupied_2d

        return {"occupied": occupied_2d, "free": free_2d}

    def check_path_clear(self, start_pose: Pose, distance: float,
                         width: float = 0.20, z_range: Tuple[float, float] = (0.1, 0.8)) -> bool:
        """
        Check if a straight-line path ahead is clear of obstacles.
        
        Args:
            start_pose: Starting pose
            distance: How far to check (meters)
            width: Robot width to check (meters)
            z_range: Height range to check for obstacles
            
        Returns:
            True if path appears clear
        """
        steps = int(distance / self.resolution)
        half_width_steps = int((width / 2) / self.resolution) + 1

        cos_theta = math.cos(start_pose.theta)
        sin_theta = math.sin(start_pose.theta)

        for i in range(steps):
            d = (i + 1) * self.resolution
            # Center of path at this distance
            cx = start_pose.x + d * cos_theta
            cy = start_pose.y + d * sin_theta

            # Check across width
            for w in range(-half_width_steps, half_width_steps + 1):
                wx = cx - w * self.resolution * sin_theta
                wy = cy + w * self.resolution * cos_theta

                # Check height range
                for z in np.arange(z_range[0], z_range[1], self.resolution):
                    if self.is_occupied(wx, wy, z):
                        return False

        return True

    @property
    def num_voxels(self) -> int:
        """Number of voxels in the grid."""
        return len(self.grid)

    @property
    def memory_estimate_kb(self) -> float:
        """Rough memory estimate in KB."""
        # Each voxel: 3 ints (key) + 1 bool + 1 float ≈ 20 bytes
        return self.num_voxels * 20 / 1024

    def should_save(self) -> bool:
        """Check if it's time to auto-save."""
        return time.time() - self.last_save_time >= config.OCTOMAP_SAVE_INTERVAL

    def save(self, filepath: str = config.OCTOMAP_FILE):
        """
        Save voxel grid to binary file.
        Format: resolution (float32) + N * (vx, vy, vz as int16, log_odds as float16)
        """
        occupied_cells = [(k, v) for k, v in self.grid.items() if v.occupied]

        with open(filepath, 'wb') as f:
            # Header
            f.write(struct.pack('f', self.resolution))
            f.write(struct.pack('I', len(occupied_cells)))

            # Voxel data
            for (vx, vy, vz), cell in occupied_cells:
                f.write(struct.pack('hhh', vx, vy, vz))
                f.write(struct.pack('e', cell.log_odds))  # float16

        self.last_save_time = time.time()
        size_kb = self.memory_estimate_kb
        print(f"[VoxelMap] Saved {len(occupied_cells)} voxels to {filepath} (~{size_kb:.1f}KB)")

    def load(self, filepath: str = config.OCTOMAP_FILE) -> bool:
        """Load voxel grid from binary file."""
        try:
            with open(filepath, 'rb') as f:
                self.resolution = struct.unpack('f', f.read(4))[0]
                count = struct.unpack('I', f.read(4))[0]

                for _ in range(count):
                    vx, vy, vz = struct.unpack('hhh', f.read(6))
                    log_odds = struct.unpack('e', f.read(2))[0]
                    cell = VoxelCell()
                    cell.log_odds = log_odds
                    cell.occupied = log_odds > 0
                    self.grid[(vx, vy, vz)] = cell

            print(f"[VoxelMap] Loaded {count} voxels from {filepath}")
            return True

        except (FileNotFoundError, struct.error) as e:
            print(f"[VoxelMap] Could not load: {e}")
            return False

    def get_stats(self) -> dict:
        """Get map statistics."""
        occupied = sum(1 for c in self.grid.values() if c.occupied)
        return {
            "total_voxels": self.num_voxels,
            "occupied_voxels": occupied,
            "free_voxels": self.num_voxels - occupied,
            "resolution_m": self.resolution,
            "memory_kb": round(self.memory_estimate_kb, 1),
            "insertions": self.total_insertions
        }


# --- Quick test ---
if __name__ == "__main__":
    vmap = VoxelMap(resolution=0.05)

    # Simulate a wall in front of the robot
    wall_points = []
    for y in np.arange(-0.5, 0.5, 0.05):
        for z in np.arange(-0.3, 0.3, 0.05):
            wall_points.append([y, z, 2.0])  # Wall at 2m in camera frame

    points = np.array(wall_points)
    robot_pose = Pose(0, 0, 0)

    vmap.insert_point_cloud(points, robot_pose)

    print(f"Stats: {vmap.get_stats()}")
    print(f"Path clear (1m): {vmap.check_path_clear(robot_pose, 1.0)}")
    print(f"Path clear (3m): {vmap.check_path_clear(robot_pose, 3.0)}")
