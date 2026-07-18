"""
Tests for Odometry module.
"""

import sys
import os
import math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jetson'))

from odometry import Pose, EncoderOdometry, OdometryFusion
import config


def test_pose_creation():
    """Pose should initialize correctly."""
    p = Pose(1.0, 2.0, 0.5)
    assert p.x == 1.0
    assert p.y == 2.0
    assert p.theta == 0.5
    print("✓ test_pose_creation passed")


def test_pose_distance():
    """Distance between poses should be Euclidean."""
    p1 = Pose(0, 0, 0)
    p2 = Pose(3, 4, 0)
    assert abs(p1.distance_to(p2) - 5.0) < 0.001
    print("✓ test_pose_distance passed")


def test_straight_line_odometry():
    """Equal ticks on both wheels = straight line."""
    odom = EncoderOdometry()

    # Drive forward 100 ticks on each wheel
    for _ in range(100):
        odom.update(1, 1)

    # Should have moved forward, no rotation
    expected_distance = 100 * config.METERS_PER_TICK
    assert abs(odom.pose.x - expected_distance) < 0.001
    assert abs(odom.pose.y) < 0.001
    assert abs(odom.pose.theta) < 0.01
    print("✓ test_straight_line_odometry passed")


def test_pure_rotation():
    """Opposite ticks = rotation in place."""
    odom = EncoderOdometry()

    # Turn: left backward, right forward
    ticks = 50
    for _ in range(ticks):
        odom.update(-1, 1)

    # Should have rotated but not moved
    assert abs(odom.pose.x) < 0.01
    assert abs(odom.pose.y) < 0.01
    assert abs(odom.pose.theta) > 0.1  # Should have turned significantly
    print("✓ test_pure_rotation passed")


def test_square_path():
    """Driving a square should return close to origin."""
    odom = EncoderOdometry()

    # Calculate ticks for 90-degree turn
    turn_arc = (math.pi / 2) * config.WHEEL_BASE / 2  # Arc length per wheel for 90°
    turn_ticks = int(turn_arc / config.METERS_PER_TICK)

    # Calculate ticks for 0.5m straight
    straight_ticks = int(0.5 / config.METERS_PER_TICK)

    # Drive a square: forward, turn right, forward, turn right, forward, turn right, forward
    for side in range(4):
        # Straight
        for _ in range(straight_ticks):
            odom.update(1, 1)
        # Turn right 90°
        for _ in range(turn_ticks):
            odom.update(1, -1)

    # Should be back near origin
    # (Allow some drift due to discrete ticks)
    assert odom.pose.distance_to(Pose(0, 0, 0)) < 0.15  # Within 15cm
    print(f"✓ test_square_path passed (drift: {odom.pose.distance_to(Pose(0, 0, 0)):.3f}m)")


def test_odometry_fusion_no_visual():
    """Fusion without visual data should fall back to encoder only."""
    fusion = OdometryFusion()

    # Update with encoder only
    for _ in range(50):
        fusion.update(left_ticks=1, right_ticks=1)

    expected_distance = 50 * config.METERS_PER_TICK
    assert abs(fusion.pose.x - expected_distance) < 0.001
    print("✓ test_odometry_fusion_no_visual passed")


def test_odometry_reset():
    """Reset should return to origin."""
    fusion = OdometryFusion()
    fusion.update(10, 10)
    assert fusion.pose.x > 0

    fusion.reset()
    assert fusion.pose.x == 0
    assert fusion.pose.y == 0
    assert fusion.pose.theta == 0
    print("✓ test_odometry_reset passed")


if __name__ == "__main__":
    test_pose_creation()
    test_pose_distance()
    test_straight_line_odometry()
    test_pure_rotation()
    test_square_path()
    test_odometry_fusion_no_visual()
    test_odometry_reset()
    print("\nAll odometry tests passed! ✓")
