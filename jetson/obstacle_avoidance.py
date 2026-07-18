"""
Warehouse AGV - Local Obstacle Avoidance

Reactive obstacle avoidance using depth data from RealSense.
Divides the depth image into zones and makes immediate movement decisions.
Escalates to remote planner when uncertain.
"""

import numpy as np
from enum import Enum
from typing import Tuple

import config


class AvoidanceAction(Enum):
    """Possible avoidance actions."""
    FORWARD = "forward"          # Path is clear, continue forward
    SLOW_FORWARD = "slow"        # Obstacle ahead but far, slow down
    STEER_LEFT = "steer_left"    # Obstacle on right, steer left
    STEER_RIGHT = "steer_right"  # Obstacle on left, steer right
    STOP = "stop"                # Obstacle too close, stop
    UNCERTAIN = "uncertain"      # Can't decide, escalate to planner


class ZoneStatus:
    """Status of a depth zone."""

    def __init__(self, name: str, min_distance: float, mean_distance: float, obstacle_fraction: float):
        self.name = name
        self.min_distance = min_distance
        self.mean_distance = mean_distance
        self.obstacle_fraction = obstacle_fraction  # Fraction of pixels with obstacle

    def __repr__(self):
        return f"{self.name}: min={self.min_distance:.2f}m, mean={self.mean_distance:.2f}m, blocked={self.obstacle_fraction:.0%}"


class ObstacleAvoidance:
    """
    Depth-based reactive obstacle avoidance.
    
    Divides the depth image into left/center/right zones.
    Makes movement decisions based on obstacle distances in each zone.
    """

    def __init__(self):
        self.stop_distance = config.OBSTACLE_STOP_DISTANCE
        self.slow_distance = config.OBSTACLE_SLOW_DISTANCE
        self.clear_distance = config.OBSTACLE_CLEAR_DISTANCE
        self.confidence_threshold = config.AVOIDANCE_CONFIDENCE_THRESHOLD

        # Zone boundaries (pixel columns)
        self.center_start = int(config.PROCESS_WIDTH * config.SIDE_ZONE_WIDTH)
        self.center_end = int(config.PROCESS_WIDTH * (1 - config.SIDE_ZONE_WIDTH))

        # Only look at the middle portion of the image vertically
        # (ignore floor close to robot and ceiling)
        self.v_start = int(config.PROCESS_HEIGHT * 0.3)
        self.v_end = int(config.PROCESS_HEIGHT * 0.8)

    def analyze_zone(self, depth_meters: np.ndarray, col_start: int, col_end: int) -> ZoneStatus:
        """
        Analyze a vertical strip of the depth image for obstacles.
        
        Args:
            depth_meters: Full depth image in meters
            col_start: Left column of the zone
            col_end: Right column of the zone
            
        Returns:
            ZoneStatus with distance metrics
        """
        zone = depth_meters[self.v_start:self.v_end, col_start:col_end]

        # Filter valid depth (ignore zeros and very far)
        valid = zone[(zone > 0.1) & (zone < config.OCTOMAP_MAX_RANGE)]

        if len(valid) == 0:
            # No valid depth data - treat as uncertain
            return ZoneStatus("unknown", float('inf'), float('inf'), 0.0)

        min_dist = float(np.min(valid))
        mean_dist = float(np.mean(valid))

        # Fraction of pixels that have an obstacle within slow_distance
        obstacle_pixels = np.sum(valid < self.slow_distance)
        total_pixels = len(valid)
        obstacle_fraction = obstacle_pixels / total_pixels

        return ZoneStatus("zone", min_dist, mean_dist, obstacle_fraction)

    def decide(self, depth_meters: np.ndarray) -> Tuple[AvoidanceAction, float, dict]:
        """
        Make an avoidance decision based on depth data.
        
        Args:
            depth_meters: Aligned depth image in meters (PROCESS_HEIGHT x PROCESS_WIDTH)
            
        Returns:
            Tuple of (action, confidence, debug_info)
            - action: What the robot should do
            - confidence: How confident we are (0-1)
            - debug_info: Zone statuses for logging/debugging
        """
        if depth_meters is None:
            return AvoidanceAction.STOP, 0.0, {"error": "no depth data"}

        # Analyze three zones
        left_zone = self.analyze_zone(depth_meters, 0, self.center_start)
        center_zone = self.analyze_zone(depth_meters, self.center_start, self.center_end)
        right_zone = self.analyze_zone(depth_meters, self.center_end, config.PROCESS_WIDTH)

        left_zone.name = "left"
        center_zone.name = "center"
        right_zone.name = "right"

        debug_info = {
            "left": {"min": left_zone.min_distance, "blocked": left_zone.obstacle_fraction},
            "center": {"min": center_zone.min_distance, "blocked": center_zone.obstacle_fraction},
            "right": {"min": right_zone.min_distance, "blocked": right_zone.obstacle_fraction},
        }

        # Decision logic
        center_clear = center_zone.min_distance > self.clear_distance
        center_slow = center_zone.min_distance > self.slow_distance
        center_blocked = center_zone.min_distance < self.stop_distance

        left_clear = left_zone.min_distance > self.slow_distance
        right_clear = right_zone.min_distance > self.slow_distance

        left_blocked = left_zone.min_distance < self.stop_distance
        right_blocked = right_zone.min_distance < self.stop_distance

        # --- Decision Rules ---

        # Rule 1: Everything clear - go forward with high confidence
        if center_clear and left_clear and right_clear:
            return AvoidanceAction.FORWARD, 0.95, debug_info

        # Rule 2: Center clear but sides have something - slow but continue
        if center_clear and (not left_clear or not right_clear):
            return AvoidanceAction.SLOW_FORWARD, 0.8, debug_info

        # Rule 3: Center has something far - slow down
        if center_slow and not center_blocked:
            return AvoidanceAction.SLOW_FORWARD, 0.75, debug_info

        # Rule 4: Center blocked, one side clear - steer
        if center_blocked or not center_slow:
            if right_clear and not left_clear:
                return AvoidanceAction.STEER_RIGHT, 0.7, debug_info
            elif left_clear and not right_clear:
                return AvoidanceAction.STEER_LEFT, 0.7, debug_info
            elif left_clear and right_clear:
                # Both sides clear, center blocked - pick the side with more space
                if left_zone.mean_distance > right_zone.mean_distance:
                    return AvoidanceAction.STEER_LEFT, 0.65, debug_info
                else:
                    return AvoidanceAction.STEER_RIGHT, 0.65, debug_info

        # Rule 5: Everything blocked - stop
        if center_blocked and left_blocked and right_blocked:
            return AvoidanceAction.STOP, 0.9, debug_info

        # Rule 6: Uncertain - can't make a clear decision
        # This triggers escalation to the remote planner
        confidence = 0.4  # Low confidence
        if center_zone.min_distance < self.stop_distance:
            return AvoidanceAction.STOP, confidence, debug_info
        else:
            return AvoidanceAction.UNCERTAIN, confidence, debug_info

    def should_escalate(self, confidence: float) -> bool:
        """Check if confidence is too low and we should ask the remote planner."""
        return confidence < self.confidence_threshold


# --- Quick test ---
if __name__ == "__main__":
    avoidance = ObstacleAvoidance()

    # Simulate a depth frame with a centered obstacle
    fake_depth = np.ones((config.PROCESS_HEIGHT, config.PROCESS_WIDTH), dtype=np.float32) * 2.0
    # Add obstacle in center
    fake_depth[80:160, 100:220] = 0.3

    action, confidence, debug = avoidance.decide(fake_depth)
    print(f"Action: {action.value}, Confidence: {confidence:.2f}")
    print(f"Debug: {debug}")
    print(f"Should escalate: {avoidance.should_escalate(confidence)}")

    # Test clear path
    clear_depth = np.ones((config.PROCESS_HEIGHT, config.PROCESS_WIDTH), dtype=np.float32) * 3.0
    action, confidence, debug = avoidance.decide(clear_depth)
    print(f"\nClear path - Action: {action.value}, Confidence: {confidence:.2f}")
