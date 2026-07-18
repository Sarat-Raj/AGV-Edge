"""
Warehouse AGV - Remote Planner Server

FastAPI REST API that runs on the MacBook.
Uses MoondreamV2 (VLM) for scene understanding and Phi-3 Mini (LLM) for navigation planning.
Both models served via Ollama.

Endpoints:
    POST /describe  - Image → scene description (VLM)
    POST /plan      - Context → movement instructions (LLM)
    POST /goal      - Set navigation goal → route plan (LLM)
    POST /help      - Image + context → help response (VLM + LLM)
    GET  /health    - Server health check
"""

import base64
import json
import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from vlm_service import VLMService
from llm_service import LLMService
from prompts import SYSTEM_PROMPT, PLANNING_PROMPT, GOAL_PROMPT, HELP_PROMPT

app = FastAPI(title="Warehouse AGV Planner", version="1.0.0")

# Initialize model services
vlm = VLMService()
llm = LLMService()


# --- Request/Response Models ---

class DescribeRequest(BaseModel):
    image: str  # Base64 encoded JPEG
    prompt: Optional[str] = None


class DescribeResponse(BaseModel):
    description: str
    processing_time_ms: float


class PlanRequest(BaseModel):
    semantic_map: dict
    current_position: dict
    goal: Optional[str] = None
    scene_description: Optional[str] = None
    obstacle_info: Optional[dict] = None


class GoalRequest(BaseModel):
    goal: str
    semantic_map: dict
    current_position: dict


class HelpRequest(BaseModel):
    image: str  # Base64 encoded JPEG
    semantic_map: dict
    current_position: dict
    situation: str


class InstructionItem(BaseModel):
    action: str
    distance: float = 0.0
    degrees: float = 0.0
    speed: str = "normal"
    reason: str = ""
    confidence: float = 0.5


class PlanResponse(BaseModel):
    instructions: list[InstructionItem]
    reasoning: str = ""
    processing_time_ms: float = 0.0


# --- Endpoints ---

@app.get("/health")
async def health_check():
    """Check server and model availability."""
    return {
        "status": "ok",
        "vlm_ready": vlm.is_ready(),
        "llm_ready": llm.is_ready(),
        "timestamp": time.time()
    }


@app.post("/describe", response_model=DescribeResponse)
async def describe_scene(request: DescribeRequest):
    """Send an image to the VLM for scene description."""
    start = time.time()

    try:
        image_bytes = base64.b64decode(request.image)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image")

    prompt = request.prompt or (
        "Describe what you see in this warehouse image. "
        "Focus on: obstacles, aisle signs/labels, floor markings, "
        "people, forklifts, shelving, and clear paths. "
        "Be concise and factual."
    )

    description = vlm.describe(image_bytes, prompt)
    if description is None:
        raise HTTPException(status_code=500, detail="VLM processing failed")

    elapsed_ms = (time.time() - start) * 1000
    return DescribeResponse(description=description, processing_time_ms=elapsed_ms)


@app.post("/plan", response_model=PlanResponse)
async def get_plan(request: PlanRequest):
    """Get movement instructions from the LLM based on context."""
    start = time.time()

    # Build context for the LLM
    context = _build_planning_context(
        semantic_map=request.semantic_map,
        current_position=request.current_position,
        goal=request.goal,
        scene_description=request.scene_description,
        obstacle_info=request.obstacle_info
    )

    # Query LLM
    response_text = llm.plan(PLANNING_PROMPT.format(context=context))
    if response_text is None:
        raise HTTPException(status_code=500, detail="LLM planning failed")

    # Parse LLM response into structured instructions
    instructions = _parse_instructions(response_text)
    elapsed_ms = (time.time() - start) * 1000

    return PlanResponse(
        instructions=instructions,
        reasoning=response_text,
        processing_time_ms=elapsed_ms
    )


@app.post("/goal", response_model=PlanResponse)
async def set_goal(request: GoalRequest):
    """Set a navigation goal and get a route plan."""
    start = time.time()

    context = _build_planning_context(
        semantic_map=request.semantic_map,
        current_position=request.current_position,
        goal=request.goal
    )

    prompt = GOAL_PROMPT.format(goal=request.goal, context=context)
    response_text = llm.plan(prompt)

    if response_text is None:
        raise HTTPException(status_code=500, detail="LLM goal planning failed")

    instructions = _parse_instructions(response_text)
    elapsed_ms = (time.time() - start) * 1000

    return PlanResponse(
        instructions=instructions,
        reasoning=response_text,
        processing_time_ms=elapsed_ms
    )


@app.post("/help", response_model=PlanResponse)
async def get_help(request: HelpRequest):
    """Handle an escalation: describe scene + plan action."""
    start = time.time()

    # Step 1: Get scene description from VLM
    try:
        image_bytes = base64.b64decode(request.image)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image")

    scene_description = vlm.describe(
        image_bytes,
        "Describe what you see ahead of this robot in a warehouse. "
        "Focus on obstacles, clearances, and possible paths."
    )

    # Step 2: Plan with LLM using scene + context
    context = _build_planning_context(
        semantic_map=request.semantic_map,
        current_position=request.current_position,
        scene_description=scene_description
    )

    prompt = HELP_PROMPT.format(
        situation=request.situation,
        scene=scene_description or "Scene description unavailable",
        context=context
    )

    response_text = llm.plan(prompt)
    if response_text is None:
        # Fallback: simple stop instruction
        return PlanResponse(
            instructions=[InstructionItem(action="stop", reason="Planner unavailable")],
            reasoning="LLM unavailable, defaulting to stop",
            processing_time_ms=(time.time() - start) * 1000
        )

    instructions = _parse_instructions(response_text)
    elapsed_ms = (time.time() - start) * 1000

    return PlanResponse(
        instructions=instructions,
        reasoning=response_text,
        processing_time_ms=elapsed_ms
    )


# --- Helpers ---

def _build_planning_context(semantic_map: dict, current_position: dict,
                            goal: Optional[str] = None,
                            scene_description: Optional[str] = None,
                            obstacle_info: Optional[dict] = None) -> str:
    """Build a text context string for the LLM from structured data."""
    parts = []

    # Current position
    pos = current_position
    parts.append(f"Current robot position: x={pos.get('x', 0):.2f}m, "
                 f"y={pos.get('y', 0):.2f}m, "
                 f"heading={pos.get('theta', 0):.1f} radians")

    # Semantic map
    layout = semantic_map.get("layout_description", "No layout information available.")
    parts.append(f"\n{layout}")

    # Goal
    if goal:
        parts.append(f"\nNavigation goal: Reach aisle {goal}")
        # Check if goal is in known landmarks
        landmarks = semantic_map.get("landmarks", {})
        if goal in landmarks:
            lm = landmarks[goal]
            parts.append(f"  Target location: ({lm['x']:.2f}, {lm['y']:.2f})")
        else:
            parts.append(f"  WARNING: Aisle {goal} has not been discovered yet!")

    # Scene description
    if scene_description:
        parts.append(f"\nCurrent camera view: {scene_description}")

    # Obstacle info
    if obstacle_info:
        parts.append(f"\nObstacle sensors: left={obstacle_info.get('left', {}).get('min', '?')}m, "
                     f"center={obstacle_info.get('center', {}).get('min', '?')}m, "
                     f"right={obstacle_info.get('right', {}).get('min', '?')}m")

    return "\n".join(parts)


def _parse_instructions(llm_response: str) -> list[InstructionItem]:
    """
    Parse LLM text response into structured instructions.
    
    The LLM is prompted to output JSON, but we handle cases where it doesn't.
    """
    # Try to find JSON in the response
    try:
        # Look for JSON array in the response
        start_idx = llm_response.find('[')
        end_idx = llm_response.rfind(']') + 1
        if start_idx != -1 and end_idx > start_idx:
            json_str = llm_response[start_idx:end_idx]
            parsed = json.loads(json_str)
            instructions = []
            for item in parsed:
                instructions.append(InstructionItem(
                    action=item.get("action", "stop"),
                    distance=item.get("distance", 0.0),
                    degrees=item.get("degrees", 0.0),
                    speed=item.get("speed", "normal"),
                    reason=item.get("reason", ""),
                    confidence=item.get("confidence", 0.5)
                ))
            return instructions
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # Fallback: try to extract simple actions from text
    response_lower = llm_response.lower()
    instructions = []

    if "turn left" in response_lower:
        instructions.append(InstructionItem(action="turn_left", degrees=90, reason="LLM suggested turn left"))
    elif "turn right" in response_lower:
        instructions.append(InstructionItem(action="turn_right", degrees=90, reason="LLM suggested turn right"))

    if "forward" in response_lower or "go straight" in response_lower or "move ahead" in response_lower:
        instructions.append(InstructionItem(action="forward", distance=1.0, reason="LLM suggested forward"))

    if "stop" in response_lower or "wait" in response_lower:
        instructions.append(InstructionItem(action="stop", reason="LLM suggested stop"))

    if "explore" in response_lower:
        instructions.append(InstructionItem(action="explore", reason="LLM suggested exploration"))

    # If nothing parsed, default to explore
    if not instructions:
        instructions.append(InstructionItem(action="explore", reason="Could not parse LLM response"))

    return instructions


# --- Entry Point ---
if __name__ == "__main__":
    print("=" * 50)
    print("  Warehouse AGV - Remote Planner Server")
    print("=" * 50)
    print(f"\n  VLM: MoondreamV2 via Ollama")
    print(f"  LLM: Phi-3 Mini via Ollama")
    print(f"  Listening on: 0.0.0.0:8000")
    print("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=8000)
