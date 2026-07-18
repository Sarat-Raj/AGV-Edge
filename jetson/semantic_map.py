"""
Warehouse AGV - Semantic Map

Maps aisle labels to positions discovered during exploration.
Enables the LLM planner to reason about warehouse layout.
"""

import json
import time
from typing import Dict, List, Optional, Tuple

import config
from odometry import Pose


class SemanticLandmark:
    """A discovered aisle sign with its position."""

    def __init__(self, label: str, x: float, y: float, heading: float,
                 confidence: float, timestamp: float):
        self.label = label
        self.x = x
        self.y = y
        self.heading = heading  # Robot heading when sign was spotted
        self.confidence = confidence
        self.timestamp = timestamp
        self.visit_count = 1

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "heading": round(self.heading, 3),
            "confidence": round(self.confidence, 2),
            "timestamp": self.timestamp,
            "visit_count": self.visit_count
        }

    def __repr__(self):
        return f"Landmark('{self.label}' @ ({self.x:.2f}, {self.y:.2f}))"


class SemanticMap:
    """
    Maintains a map of discovered aisle labels and their positions.
    
    As the robot explores and reads signs, it builds up knowledge of
    the warehouse layout. This is sent to the LLM planner for reasoning.
    """

    def __init__(self):
        self.landmarks: Dict[str, SemanticLandmark] = {}
        self.exploration_path: List[Tuple[float, float]] = []  # Breadcrumb trail
        self._last_breadcrumb_time = 0
        self._breadcrumb_interval = 2.0  # seconds

    def add_landmark(self, label: str, pose: Pose, confidence: float):
        """
        Add or update a landmark in the semantic map.
        
        If the label already exists, update position with a running average
        (weighted by confidence).
        """
        if label in self.landmarks:
            existing = self.landmarks[label]
            # Weighted average update
            total_conf = existing.confidence + confidence
            existing.x = (existing.x * existing.confidence + pose.x * confidence) / total_conf
            existing.y = (existing.y * existing.confidence + pose.y * confidence) / total_conf
            existing.confidence = min(1.0, total_conf)  # Cap at 1.0
            existing.visit_count += 1
            existing.timestamp = time.time()
            print(f"[SemanticMap] Updated: {existing}")
        else:
            landmark = SemanticLandmark(
                label=label,
                x=pose.x,
                y=pose.y,
                heading=pose.theta,
                confidence=confidence,
                timestamp=time.time()
            )
            self.landmarks[label] = landmark
            print(f"[SemanticMap] Discovered: {landmark}")

    def add_breadcrumb(self, pose: Pose):
        """Add a position breadcrumb for path tracking."""
        now = time.time()
        if now - self._last_breadcrumb_time >= self._breadcrumb_interval:
            self.exploration_path.append((pose.x, pose.y))
            self._last_breadcrumb_time = now
            # Keep path manageable
            if len(self.exploration_path) > 500:
                # Downsample: keep every other point
                self.exploration_path = self.exploration_path[::2]

    def get_landmark(self, label: str) -> Optional[SemanticLandmark]:
        """Get a landmark by its label."""
        return self.landmarks.get(label)

    def get_nearest_landmark(self, pose: Pose) -> Optional[SemanticLandmark]:
        """Find the nearest known landmark to the current position."""
        if not self.landmarks:
            return None

        nearest = None
        min_dist = float('inf')
        for landmark in self.landmarks.values():
            dist = ((landmark.x - pose.x) ** 2 + (landmark.y - pose.y) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                nearest = landmark

        return nearest

    def get_layout_description(self) -> str:
        """
        Generate a natural language description of the discovered layout.
        This is sent to the LLM planner for reasoning.
        """
        if not self.landmarks:
            return "No aisle signs have been discovered yet. The robot needs to explore."

        # Sort landmarks by label
        sorted_landmarks = sorted(self.landmarks.values(), key=lambda l: l.label)

        lines = ["Discovered warehouse layout:"]
        for lm in sorted_landmarks:
            lines.append(f"  - Aisle {lm.label} is at position ({lm.x:.1f}, {lm.y:.1f}), "
                         f"visited {lm.visit_count} time(s)")

        # Try to infer aisle ordering
        if len(sorted_landmarks) >= 2:
            lines.append("\nInferred spatial relationships:")
            for i in range(len(sorted_landmarks) - 1):
                a = sorted_landmarks[i]
                b = sorted_landmarks[i + 1]
                dx = b.x - a.x
                dy = b.y - a.y
                dist = (dx ** 2 + dy ** 2) ** 0.5

                if abs(dx) > abs(dy):
                    direction = "to the right" if dx > 0 else "to the left"
                else:
                    direction = "ahead" if dy > 0 else "behind"

                lines.append(f"  - {b.label} is {dist:.1f}m {direction} of {a.label}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize semantic map to dictionary (for JSON/API)."""
        return {
            "landmarks": {label: lm.to_dict() for label, lm in self.landmarks.items()},
            "num_landmarks": len(self.landmarks),
            "exploration_distance": self._compute_path_length(),
            "layout_description": self.get_layout_description()
        }

    def _compute_path_length(self) -> float:
        """Compute total distance traveled."""
        if len(self.exploration_path) < 2:
            return 0.0
        total = 0.0
        for i in range(1, len(self.exploration_path)):
            dx = self.exploration_path[i][0] - self.exploration_path[i - 1][0]
            dy = self.exploration_path[i][1] - self.exploration_path[i - 1][1]
            total += (dx ** 2 + dy ** 2) ** 0.5
        return total

    def save(self, filepath: str = config.SEMANTIC_MAP_FILE):
        """Save semantic map to JSON file."""
        data = self.to_dict()
        data["path"] = self.exploration_path[-100:]  # Save last 100 breadcrumbs

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"[SemanticMap] Saved to {filepath}")

    def load(self, filepath: str = config.SEMANTIC_MAP_FILE) -> bool:
        """Load semantic map from JSON file."""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)

            for label, lm_data in data.get("landmarks", {}).items():
                self.landmarks[label] = SemanticLandmark(
                    label=lm_data["label"],
                    x=lm_data["x"],
                    y=lm_data["y"],
                    heading=lm_data.get("heading", 0),
                    confidence=lm_data["confidence"],
                    timestamp=lm_data["timestamp"]
                )
                self.landmarks[label].visit_count = lm_data.get("visit_count", 1)

            self.exploration_path = data.get("path", [])
            print(f"[SemanticMap] Loaded {len(self.landmarks)} landmarks from {filepath}")
            return True

        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[SemanticMap] Could not load: {e}")
            return False

    def knows_location(self, label: str) -> bool:
        """Check if a specific aisle label has been discovered."""
        return label in self.landmarks


# --- Quick test ---
if __name__ == "__main__":
    smap = SemanticMap()

    # Simulate discovering aisles
    smap.add_landmark("H2", Pose(0.0, 0.0, 0.0), confidence=0.8)
    smap.add_landmark("H3", Pose(3.1, 0.1, 0.0), confidence=0.9)
    smap.add_landmark("H4", Pose(6.0, 0.0, 0.0), confidence=0.85)
    smap.add_landmark("H5", Pose(9.1, -0.1, 0.0), confidence=0.7)

    print(smap.get_layout_description())
    print(f"\nKnows H4: {smap.knows_location('H4')}")
    print(f"Knows J1: {smap.knows_location('J1')}")

    # Serialize
    print(f"\nJSON: {json.dumps(smap.to_dict(), indent=2)}")
