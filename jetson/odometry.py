"""
Warehouse AGV - Odometry Fusion

Fuses wheel encoder odometry with visual odometry from RealSense
to produce a robust pose estimate (x, y, heading).

Uses a complementary filter for simplicity on Jetson Nano.
"""

import math
import time
import numpy as np
from typing import Tuple, Optional

import cv2

import config


class Pose:
    """Robot pose in 2D: (x, y, theta)."""

    def __init__(self, x: float = 0.0, y: float = 0.0, theta: float = 0.0):
        self.x = x
        self.y = y
        self.theta = theta  # radians, 0 = forward, positive = counter-clockwise

    def __repr__(self):
        return f"Pose(x={self.x:.3f}, y={self.y:.3f}, theta={math.degrees(self.theta):.1f}°)"

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "theta": self.theta}

    def distance_to(self, other: 'Pose') -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)


class EncoderOdometry:
    """Differential drive odometry from wheel encoders."""

    def __init__(self):
        self.wheel_base = config.WHEEL_BASE
        self.meters_per_tick = config.METERS_PER_TICK
        self.pose = Pose()

    def update(self, left_ticks: int, right_ticks: int) -> Pose:
        """
        Update pose estimate from encoder tick deltas.
        
        Args:
            left_ticks: Left wheel tick delta since last update
            right_ticks: Right wheel tick delta since last update
            
        Returns:
            Updated pose
        """
        # Convert ticks to distance
        dl = left_ticks * self.meters_per_tick
        dr = right_ticks * self.meters_per_tick

        # Differential drive kinematics
        dc = (dl + dr) / 2.0  # Center distance
        dtheta = (dr - dl) / self.wheel_base  # Turn angle

        # Update pose
        if abs(dtheta) < 1e-6:
            # Straight line
            self.pose.x += dc * math.cos(self.pose.theta)
            self.pose.y += dc * math.sin(self.pose.theta)
        else:
            # Arc motion
            radius = dc / dtheta
            self.pose.x += radius * (math.sin(self.pose.theta + dtheta) - math.sin(self.pose.theta))
            self.pose.y -= radius * (math.cos(self.pose.theta + dtheta) - math.cos(self.pose.theta))
            self.pose.theta += dtheta

        # Normalize theta to [-pi, pi]
        self.pose.theta = math.atan2(math.sin(self.pose.theta), math.cos(self.pose.theta))

        return self.pose

    def reset(self):
        """Reset pose to origin."""
        self.pose = Pose()


class VisualOdometry:
    """
    Simple visual odometry using feature matching between consecutive frames.
    Uses RealSense depth to scale the motion estimate.
    """

    def __init__(self):
        self.prev_frame = None
        self.prev_keypoints = None
        self.prev_descriptors = None
        self.prev_depth = None

        # ORB feature detector (fast, good for Jetson)
        self.detector = cv2.ORB_create(nfeatures=500)
        # Brute-force matcher
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

        self.pose = Pose()

    def update(self, color_frame: np.ndarray, depth_meters: np.ndarray) -> Optional[Tuple[float, float, float]]:
        """
        Estimate motion from frame-to-frame feature matching.
        
        Args:
            color_frame: BGR image (PROCESS_WIDTH x PROCESS_HEIGHT)
            depth_meters: Aligned depth in meters
            
        Returns:
            Tuple of (dx, dy, dtheta) in robot frame, or None if tracking lost
        """
        # Convert to grayscale
        gray = cv2.cvtColor(color_frame, cv2.COLOR_BGR2GRAY)

        # Detect features
        keypoints, descriptors = self.detector.detectAndCompute(gray, None)

        if descriptors is None or len(keypoints) < 10:
            self.prev_frame = gray
            self.prev_keypoints = keypoints
            self.prev_descriptors = descriptors
            self.prev_depth = depth_meters
            return None

        # First frame - just store
        if self.prev_descriptors is None:
            self.prev_frame = gray
            self.prev_keypoints = keypoints
            self.prev_descriptors = descriptors
            self.prev_depth = depth_meters
            return None

        # Match features
        try:
            matches = self.matcher.match(self.prev_descriptors, descriptors)
        except cv2.error:
            self.prev_frame = gray
            self.prev_keypoints = keypoints
            self.prev_descriptors = descriptors
            self.prev_depth = depth_meters
            return None

        if len(matches) < 10:
            self.prev_frame = gray
            self.prev_keypoints = keypoints
            self.prev_descriptors = descriptors
            self.prev_depth = depth_meters
            return None

        # Sort by distance (quality)
        matches = sorted(matches, key=lambda m: m.distance)[:50]

        # Get matched point coordinates
        prev_pts = np.float32([self.prev_keypoints[m.queryIdx].pt for m in matches])
        curr_pts = np.float32([keypoints[m.trainIdx].pt for m in matches])

        # Estimate essential matrix / fundamental matrix
        # For simplicity, use 2D motion estimation from matched points
        # Compute average displacement
        displacements = curr_pts - prev_pts

        # Get depth at matched points for scaling
        depths = []
        for pt in prev_pts:
            px, py = int(pt[0]), int(pt[1])
            if 0 <= py < depth_meters.shape[0] and 0 <= px < depth_meters.shape[1]:
                d = self.prev_depth[py, px]
                if 0.3 < d < config.OCTOMAP_MAX_RANGE:
                    depths.append(d)

        if len(depths) < 5:
            self.prev_frame = gray
            self.prev_keypoints = keypoints
            self.prev_descriptors = descriptors
            self.prev_depth = depth_meters
            return None

        median_depth = np.median(depths)

        # Approximate translation from pixel displacement + depth
        # dx (forward) ~ negative vertical displacement (features move up when moving forward)
        # dy (lateral) ~ horizontal displacement
        mean_disp = np.median(displacements, axis=0)

        # Rough scale: pixels to meters using depth and focal length approximation
        focal_length = config.PROCESS_WIDTH * 0.6  # Approximate
        scale = median_depth / focal_length

        dx = -mean_disp[1] * scale  # Forward motion (negative Y displacement = forward)
        dy = -mean_disp[0] * scale  # Lateral motion

        # Estimate rotation from horizontal displacement pattern
        left_half = displacements[prev_pts[:, 0] < config.PROCESS_WIDTH / 2]
        right_half = displacements[prev_pts[:, 0] >= config.PROCESS_WIDTH / 2]

        if len(left_half) > 3 and len(right_half) > 3:
            # Rotation causes opposite horizontal motion in left vs right halves
            left_mean = np.mean(left_half[:, 0])
            right_mean = np.mean(right_half[:, 0])
            dtheta = (left_mean - right_mean) / config.PROCESS_WIDTH * 0.5  # Empirical scale
        else:
            dtheta = 0.0

        # Update visual pose
        self.pose.x += dx * math.cos(self.pose.theta) - dy * math.sin(self.pose.theta)
        self.pose.y += dx * math.sin(self.pose.theta) + dy * math.cos(self.pose.theta)
        self.pose.theta += dtheta
        self.pose.theta = math.atan2(math.sin(self.pose.theta), math.cos(self.pose.theta))

        # Store for next frame
        self.prev_frame = gray
        self.prev_keypoints = keypoints
        self.prev_descriptors = descriptors
        self.prev_depth = depth_meters

        return dx, dy, dtheta

    def reset(self):
        """Reset visual odometry."""
        self.prev_frame = None
        self.prev_keypoints = None
        self.prev_descriptors = None
        self.prev_depth = None
        self.pose = Pose()


class OdometryFusion:
    """
    Fuses encoder odometry and visual odometry using a complementary filter.
    
    Encoder odometry: good for short-term, drifts over time (wheel slip)
    Visual odometry: noisier frame-to-frame but independent of wheel contact
    """

    def __init__(self):
        self.encoder_odom = EncoderOdometry()
        self.visual_odom = VisualOdometry()
        self.fused_pose = Pose()

        self.encoder_weight = config.ENCODER_WEIGHT
        self.visual_weight = config.VISUAL_ODOM_WEIGHT

        self._last_update = time.time()

    def update(self, left_ticks: int, right_ticks: int,
               color_frame: Optional[np.ndarray] = None,
               depth_meters: Optional[np.ndarray] = None) -> Pose:
        """
        Update fused pose estimate.
        
        Args:
            left_ticks: Left encoder tick delta
            right_ticks: Right encoder tick delta
            color_frame: Optional BGR frame for visual odometry
            depth_meters: Optional depth frame for visual odometry
            
        Returns:
            Fused pose estimate
        """
        # Always update encoder odometry
        encoder_pose = self.encoder_odom.update(left_ticks, right_ticks)

        # Update visual odometry if frames provided
        visual_delta = None
        if color_frame is not None and depth_meters is not None:
            visual_delta = self.visual_odom.update(color_frame, depth_meters)

        # Complementary filter fusion
        if visual_delta is not None:
            vdx, vdy, vdtheta = visual_delta

            # Encoder-derived deltas
            edx = left_ticks * self.encoder_odom.meters_per_tick
            edy = 0  # Differential drive doesn't directly measure lateral
            edtheta = (right_ticks - left_ticks) * self.encoder_odom.meters_per_tick / config.WHEEL_BASE

            # Weighted fusion of deltas
            dx = self.encoder_weight * edx + self.visual_weight * vdx
            dy = self.visual_weight * vdy  # Only visual gives lateral
            dtheta = self.encoder_weight * edtheta + self.visual_weight * vdtheta

            # Apply fused deltas to fused pose
            self.fused_pose.x += dx * math.cos(self.fused_pose.theta) - dy * math.sin(self.fused_pose.theta)
            self.fused_pose.y += dx * math.sin(self.fused_pose.theta) + dy * math.cos(self.fused_pose.theta)
            self.fused_pose.theta += dtheta
        else:
            # No visual data - use encoder only
            dl = left_ticks * self.encoder_odom.meters_per_tick
            dr = right_ticks * self.encoder_odom.meters_per_tick
            dc = (dl + dr) / 2.0
            dtheta = (dr - dl) / config.WHEEL_BASE

            self.fused_pose.x += dc * math.cos(self.fused_pose.theta)
            self.fused_pose.y += dc * math.sin(self.fused_pose.theta)
            self.fused_pose.theta += dtheta

        # Normalize theta
        self.fused_pose.theta = math.atan2(
            math.sin(self.fused_pose.theta),
            math.cos(self.fused_pose.theta)
        )

        self._last_update = time.time()
        return self.fused_pose

    @property
    def pose(self) -> Pose:
        """Get current fused pose."""
        return self.fused_pose

    def reset(self):
        """Reset all odometry to origin."""
        self.encoder_odom.reset()
        self.visual_odom.reset()
        self.fused_pose = Pose()


# --- Quick test ---
if __name__ == "__main__":
    odom = OdometryFusion()

    # Simulate driving forward 100 ticks on each wheel
    for i in range(10):
        pose = odom.update(left_ticks=10, right_ticks=10)
        print(f"Step {i}: {pose}")

    print("\nTurning right...")
    for i in range(5):
        pose = odom.update(left_ticks=10, right_ticks=-10)
        print(f"Step {i}: {pose}")
