"""
Tests for the Remote Planner API.

These tests use FastAPI's TestClient to test the endpoints
without needing Ollama running (mocked models).
"""

import sys
import os
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'planner'))

# Mock ollama before importing server
import base64


def test_health_endpoint():
    """Health endpoint should return status."""
    from fastapi.testclient import TestClient

    with patch('vlm_service.VLMService') as MockVLM, \
         patch('llm_service.LLMService') as MockLLM:
        MockVLM.return_value.is_ready.return_value = True
        MockLLM.return_value.is_ready.return_value = True

        from server import app
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        print("✓ test_health_endpoint passed")


def test_plan_endpoint_known_goal():
    """Plan endpoint should return instructions for known goal."""
    from fastapi.testclient import TestClient

    with patch('llm_service.LLMService') as MockLLM:
        # Mock LLM to return structured JSON
        mock_response = json.dumps([
            {"action": "turn_right", "degrees": 90, "reason": "Face H4 direction", "confidence": 0.8},
            {"action": "forward", "distance": 3.0, "reason": "Move to H4", "confidence": 0.7}
        ])
        MockLLM.return_value.is_ready.return_value = True
        MockLLM.return_value.plan.return_value = mock_response

        from server import app
        client = TestClient(app)

        payload = {
            "goal": "H4",
            "semantic_map": {
                "landmarks": {
                    "H2": {"label": "H2", "x": 0.0, "y": 0.0},
                    "H4": {"label": "H4", "x": 6.0, "y": 0.0}
                },
                "layout_description": "H2 is at origin, H4 is 6m to the right"
            },
            "current_position": {"x": 0.0, "y": 0.0, "theta": 0.0}
        }

        response = client.post("/goal", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "instructions" in data
        assert len(data["instructions"]) == 2
        assert data["instructions"][0]["action"] == "turn_right"
        print("✓ test_plan_endpoint_known_goal passed")


def test_instruction_parsing_fallback():
    """Parser should handle non-JSON LLM responses gracefully."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'planner'))
    from server import _parse_instructions

    # Test with plain text response
    response = "I think you should turn left and then go forward about 2 meters."
    instructions = _parse_instructions(response)

    assert len(instructions) > 0
    actions = [i.action for i in instructions]
    assert "turn_left" in actions or "forward" in actions
    print("✓ test_instruction_parsing_fallback passed")


def test_instruction_parsing_json():
    """Parser should correctly parse JSON instruction arrays."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'planner'))
    from server import _parse_instructions

    response = """Here's the plan:
[
  {"action": "forward", "distance": 2.0, "speed": "normal", "reason": "Move ahead"},
  {"action": "turn_left", "degrees": 45, "speed": "slow", "reason": "Align with aisle"}
]
"""
    instructions = _parse_instructions(response)
    assert len(instructions) == 2
    assert instructions[0].action == "forward"
    assert instructions[0].distance == 2.0
    assert instructions[1].action == "turn_left"
    assert instructions[1].degrees == 45
    print("✓ test_instruction_parsing_json passed")


def test_context_builder():
    """Context builder should produce meaningful text."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'planner'))
    from server import _build_planning_context

    context = _build_planning_context(
        semantic_map={
            "landmarks": {"H4": {"x": 6.0, "y": 0.0}},
            "layout_description": "Aisle H4 at (6.0, 0.0)"
        },
        current_position={"x": 0.0, "y": 0.0, "theta": 0.0},
        goal="H4",
        scene_description="Clear aisle ahead with shelving on both sides"
    )

    assert "H4" in context
    assert "6.0" in context or "6.00" in context
    assert "Current robot position" in context
    assert "Clear aisle" in context
    print("✓ test_context_builder passed")


if __name__ == "__main__":
    # These tests can run without Ollama
    test_instruction_parsing_fallback()
    test_instruction_parsing_json()
    test_context_builder()
    print("\n(Note: test_health_endpoint and test_plan_endpoint_known_goal require FastAPI testclient)")
    print("\nAll planner tests passed! ✓")
