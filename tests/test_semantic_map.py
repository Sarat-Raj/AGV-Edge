"""
Tests for Semantic Map module.
"""

import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jetson'))

from semantic_map import SemanticMap
from odometry import Pose


def test_add_landmark():
    """Adding a landmark should store it correctly."""
    smap = SemanticMap()
    smap.add_landmark("H4", Pose(3.0, 1.0, 0.5), confidence=0.85)

    assert smap.knows_location("H4")
    assert not smap.knows_location("H5")

    lm = smap.get_landmark("H4")
    assert lm.label == "H4"
    assert abs(lm.x - 3.0) < 0.01
    assert abs(lm.y - 1.0) < 0.01
    assert lm.confidence == 0.85
    print("✓ test_add_landmark passed")


def test_update_landmark():
    """Re-observing a landmark should update with weighted average."""
    smap = SemanticMap()
    smap.add_landmark("H4", Pose(3.0, 1.0, 0.0), confidence=0.8)
    smap.add_landmark("H4", Pose(3.2, 0.8, 0.0), confidence=0.8)

    lm = smap.get_landmark("H4")
    # Should be average of (3.0, 1.0) and (3.2, 0.8) with equal weights
    assert abs(lm.x - 3.1) < 0.01
    assert abs(lm.y - 0.9) < 0.01
    assert lm.visit_count == 2
    print("✓ test_update_landmark passed")


def test_nearest_landmark():
    """Should find the nearest landmark to current pose."""
    smap = SemanticMap()
    smap.add_landmark("H1", Pose(0.0, 0.0, 0.0), 0.9)
    smap.add_landmark("H2", Pose(3.0, 0.0, 0.0), 0.9)
    smap.add_landmark("H3", Pose(6.0, 0.0, 0.0), 0.9)

    nearest = smap.get_nearest_landmark(Pose(2.5, 0.1, 0.0))
    assert nearest.label == "H2"
    print("✓ test_nearest_landmark passed")


def test_layout_description():
    """Layout description should contain discovered aisles."""
    smap = SemanticMap()
    smap.add_landmark("H2", Pose(0.0, 0.0, 0.0), 0.9)
    smap.add_landmark("H3", Pose(3.0, 0.0, 0.0), 0.9)
    smap.add_landmark("H4", Pose(6.0, 0.0, 0.0), 0.9)

    desc = smap.get_layout_description()
    assert "H2" in desc
    assert "H3" in desc
    assert "H4" in desc
    assert "Discovered warehouse layout:" in desc
    print("✓ test_layout_description passed")


def test_serialization():
    """Save and load should preserve data."""
    smap = SemanticMap()
    smap.add_landmark("A1", Pose(1.0, 2.0, 0.5), 0.9)
    smap.add_landmark("B2", Pose(4.0, 5.0, 1.0), 0.8)

    # Save to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        tmpfile = f.name

    smap.save(tmpfile)

    # Load into new instance
    smap2 = SemanticMap()
    assert smap2.load(tmpfile)
    assert smap2.knows_location("A1")
    assert smap2.knows_location("B2")

    lm = smap2.get_landmark("A1")
    assert abs(lm.x - 1.0) < 0.01

    # Cleanup
    os.unlink(tmpfile)
    print("✓ test_serialization passed")


def test_to_dict():
    """to_dict should produce valid structure for API."""
    smap = SemanticMap()
    smap.add_landmark("H4", Pose(3.0, 1.0, 0.0), 0.85)

    data = smap.to_dict()
    assert "landmarks" in data
    assert "H4" in data["landmarks"]
    assert "layout_description" in data
    assert data["num_landmarks"] == 1
    print("✓ test_to_dict passed")


def test_empty_map():
    """Empty map should handle gracefully."""
    smap = SemanticMap()
    assert smap.get_nearest_landmark(Pose(0, 0, 0)) is None
    assert "No aisle signs" in smap.get_layout_description()
    assert not smap.knows_location("H4")
    print("✓ test_empty_map passed")


if __name__ == "__main__":
    test_add_landmark()
    test_update_landmark()
    test_nearest_landmark()
    test_layout_description()
    test_serialization()
    test_to_dict()
    test_empty_map()
    print("\nAll semantic map tests passed! ✓")
