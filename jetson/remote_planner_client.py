"""
Warehouse AGV - Remote Planner Client

HTTP client that communicates with the remote VLM+LLM planner
running on the MacBook. Sends images and semantic map data,
receives movement instructions.
"""

import base64
import json
import time
from typing import Optional, Dict, List

import requests
import numpy as np

import config


class PlannerInstruction:
    """A movement instruction from the remote planner."""

    def __init__(self, action: str, **kwargs):
        self.action = action  # forward, backward, turn_left, turn_right, stop, explore
        self.distance = kwargs.get("distance", 0.0)  # meters
        self.degrees = kwargs.get("degrees", 0.0)  # degrees for turns
        self.speed = kwargs.get("speed", "normal")  # slow, normal, fast
        self.reason = kwargs.get("reason", "")  # Why this action
        self.confidence = kwargs.get("confidence", 0.5)

    def __repr__(self):
        if self.action in ("forward", "backward"):
            return f"Instruction({self.action} {self.distance:.1f}m, {self.speed})"
        elif self.action in ("turn_left", "turn_right"):
            return f"Instruction({self.action} {self.degrees:.0f}°)"
        else:
            return f"Instruction({self.action})"

    @classmethod
    def from_dict(cls, data: dict) -> 'PlannerInstruction':
        action = data.get("action", "stop")
        return cls(
            action=action,
            distance=data.get("distance", 0.0),
            degrees=data.get("degrees", 0.0),
            speed=data.get("speed", "normal"),
            reason=data.get("reason", ""),
            confidence=data.get("confidence", 0.5)
        )


class RemotePlannerClient:
    """
    Client for the remote VLM+LLM planner API.
    
    Endpoints:
        POST /describe  - Send image, get scene description
        POST /plan      - Send context, get movement instructions
        POST /goal      - Set a navigation goal
        GET  /health    - Check planner status
    """

    def __init__(self, base_url: str = config.PLANNER_URL):
        self.base_url = base_url
        self.timeout = config.PLANNER_TIMEOUT
        self.retry_count = config.PLANNER_RETRY_COUNT
        self.connected = False

        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def check_connection(self) -> bool:
        """Check if the remote planner is reachable."""
        try:
            resp = self._session.get(
                f"{self.base_url}/health",
                timeout=3
            )
            self.connected = resp.status_code == 200
            return self.connected
        except requests.exceptions.RequestException:
            self.connected = False
            return False

    def describe_scene(self, image_bytes: bytes) -> Optional[str]:
        """
        Send an image to the VLM for scene description.
        
        Args:
            image_bytes: JPEG encoded image bytes
            
        Returns:
            Scene description string, or None on failure
        """
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')

        payload = {
            "image": image_b64,
            "prompt": "Describe what you see in this warehouse image. "
                      "Focus on: obstacles, aisle signs, floor markings, "
                      "people, forklifts, and clear paths."
        }

        response = self._post("/describe", payload)
        if response:
            return response.get("description")
        return None

    def get_plan(self, semantic_map: dict, current_position: dict,
                 goal: Optional[str] = None,
                 scene_description: Optional[str] = None,
                 obstacle_info: Optional[dict] = None) -> Optional[List[PlannerInstruction]]:
        """
        Request movement plan from the LLM.
        
        Args:
            semantic_map: Serialized semantic map with landmarks
            current_position: Current robot pose {x, y, theta}
            goal: Target aisle/location (e.g., "H4")
            scene_description: Optional VLM scene description
            obstacle_info: Optional obstacle avoidance debug info
            
        Returns:
            List of PlannerInstruction, or None on failure
        """
        payload = {
            "semantic_map": semantic_map,
            "current_position": current_position,
            "goal": goal,
            "scene_description": scene_description,
            "obstacle_info": obstacle_info,
        }

        response = self._post("/plan", payload)
        if response and "instructions" in response:
            instructions = []
            for inst_data in response["instructions"]:
                instructions.append(PlannerInstruction.from_dict(inst_data))
            return instructions
        return None

    def set_goal(self, goal: str, semantic_map: dict, current_position: dict) -> Optional[List[PlannerInstruction]]:
        """
        Set a new navigation goal (e.g., "Go to aisle H4").
        
        The planner will either provide a route if the location is known,
        or suggest exploration if the goal hasn't been discovered yet.
        """
        payload = {
            "goal": goal,
            "semantic_map": semantic_map,
            "current_position": current_position,
        }

        response = self._post("/goal", payload)
        if response:
            instructions = []
            for inst_data in response.get("instructions", []):
                instructions.append(PlannerInstruction.from_dict(inst_data))
            return instructions
        return None

    def ask_for_help(self, image_bytes: bytes, semantic_map: dict,
                     current_position: dict, situation: str) -> Optional[List[PlannerInstruction]]:
        """
        Escalate an uncertain situation to the remote planner.
        Combines scene description + planning in one call.
        
        Args:
            image_bytes: Current camera view (JPEG)
            semantic_map: Current semantic map
            current_position: Current pose
            situation: Description of why help is needed
        """
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')

        payload = {
            "image": image_b64,
            "semantic_map": semantic_map,
            "current_position": current_position,
            "situation": situation,
        }

        response = self._post("/help", payload)
        if response and "instructions" in response:
            instructions = []
            for inst_data in response["instructions"]:
                instructions.append(PlannerInstruction.from_dict(inst_data))
            return instructions
        return None

    def _post(self, endpoint: str, payload: dict) -> Optional[dict]:
        """Make a POST request with retry logic."""
        url = f"{self.base_url}{endpoint}"

        for attempt in range(self.retry_count + 1):
            try:
                resp = self._session.post(url, json=payload, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.json()
                else:
                    print(f"[Planner] {endpoint} returned {resp.status_code}: {resp.text[:100]}")

            except requests.exceptions.Timeout:
                print(f"[Planner] Timeout on {endpoint} (attempt {attempt + 1})")
            except requests.exceptions.ConnectionError:
                print(f"[Planner] Connection error on {endpoint} (attempt {attempt + 1})")
                self.connected = False
            except requests.exceptions.RequestException as e:
                print(f"[Planner] Request error: {e}")
                break

            if attempt < self.retry_count:
                time.sleep(0.5 * (attempt + 1))  # Backoff

        return None


# --- Quick test ---
if __name__ == "__main__":
    client = RemotePlannerClient()

    print(f"Checking planner at {client.base_url}...")
    if client.check_connection():
        print("  ✓ Planner is online")

        # Test scene description
        # (In real use, this would be actual camera JPEG bytes)
        test_image = b'\xff\xd8\xff\xe0' + b'\x00' * 100  # Fake JPEG
        desc = client.describe_scene(test_image)
        print(f"  Scene: {desc}")

    else:
        print("  ✗ Planner not reachable")
        print("  Make sure the planner server is running on your MacBook")
        print(f"  Expected at: {client.base_url}")
