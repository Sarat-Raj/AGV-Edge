"""
Tests for Obstacle Avoidance module.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jetson'))

import numpy as np
from obstacle_avoidance import ObstacleAvoidance, AvoidanceAction
import config


def test_clear_path():
    """All clear → should return FORWARD with high confidence."""
    avoidance = ObstacleAvoidance()
    depth = np.ones((config.PROCESS_HEIGHT, config.PROCESS_WIDTH), dtype=np.float32) * 3.0

    action, confidence, debug = avoidance.decide(depth)
    assert action == AvoidanceAction.FORWARD
    assert confidence > 0.8
    print("✓ test_clear_path passed")


def test_center_obstacle_close():
    """Obstacle dead center and close → should STOP or STEER."""
    avoidance = ObstacleAvoidance()
    depth = np.ones((config.PROCESS_HEIGHT, config.PROCESS_WIDTH), dtype=np.float32) * 3.0

    # Add close obstacle in center zone
    center_start = int(config.PROCESS_WIDTH * config.SIDE_ZONE_WIDTH)
    center_end = int(config.PROCESS_WIDTH * (1 - config.SIDE_ZONE_WIDTH))
    v_start = int(config.PROCESS_HEIGHT * 0.3)
    v_end = int(config.PROCESS_HEIGHT * 0.8)
    depth[v_start:v_end, center_start:center_end] = 0.25  # 25cm - very close

    action, confidence, debug = avoidance.decide(depth)
    assert action in (AvoidanceAction.STOP, AvoidanceAction.STEER_LEFT, AvoidanceAction.STEER_RIGHT)
    print("✓ test_center_obstacle_close passed")


def test_left_obstacle():
    """Obstacle on left only → should STEER_RIGHT or continue cautiously."""
    avoidance = ObstacleAvoidance()
    depth = np.ones((config.PROCESS_HEIGHT, config.PROCESS_WIDTH), dtype=np.float32) * 3.0

    # Block left zone only
    center_start = int(config.PROCESS_WIDTH * config.SIDE_ZONE_WIDTH)
    v_start = int(config.PROCESS_HEIGHT * 0.3)
    v_end = int(config.PROCESS_HEIGHT * 0.8)
    depth[v_start:v_end, 0:center_start] = 0.3

    action, confidence, debug = avoidance.decide(depth)
    # Center is still clear, so should continue (possibly slow)
    assert action in (AvoidanceAction.FORWARD, AvoidanceAction.SLOW_FORWARD)
    print("✓ test_left_obstacle passed")


def test_all_blocked():
    """Everything blocked → should STOP."""
    avoidance = ObstacleAvoidance()
    depth = np.ones((config.PROCESS_HEIGHT, config.PROCESS_WIDTH), dtype=np.float32) * 0.25

    action, confidence, debug = avoidance.decide(depth)
    assert action == AvoidanceAction.STOP
    print("✓ test_all_blocked passed")


def test_no_depth_data():
    """No depth data → should STOP with low confidence."""
    avoidance = ObstacleAvoidance()

    action, confidence, debug = avoidance.decide(None)
    assert action == AvoidanceAction.STOP
    assert confidence == 0.0
    print("✓ test_no_depth_data passed")


def test_escalation_threshold():
    """Low confidence should trigger escalation."""
    avoidance = ObstacleAvoidance()
    assert avoidance.should_escalate(0.3) == True
    assert avoidance.should_escalate(0.8) == False
    print("✓ test_escalation_threshold passed")


if __name__ == "__main__":
    test_clear_path()
    test_center_obstacle_close()
    test_left_obstacle()
    test_all_blocked()
    test_no_depth_data()
    test_escalation_threshold()
    print("\nAll obstacle avoidance tests passed! ✓")
