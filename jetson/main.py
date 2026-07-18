"""
Warehouse AGV - Main Control Loop

Ties together all subsystems:
- Camera capture
- Odometry fusion
- OctoMap voxel mapping
- OCR sign reading
- Obstacle avoidance
- Remote planner communication
- Motor control

Operating modes:
1. EXPLORE: Drive around, read signs, build map
2. NAVIGATE: Follow planner instructions to reach a goal
3. AVOID: Actively avoiding an obstacle
4. WAITING: Stopped, waiting for planner response or user command
"""

import time
import threading
from enum import Enum
from typing import Optional, List

import config
from camera import RealSenseCamera
from motor_controller import MotorController
from odometry import OdometryFusion, Pose
from mapping import VoxelMap
from obstacle_avoidance import ObstacleAvoidance, AvoidanceAction
from ocr_reader import OCRReader
from semantic_map import SemanticMap
from remote_planner_client import RemotePlannerClient, PlannerInstruction


class AGVMode(Enum):
    EXPLORE = "explore"
    NAVIGATE = "navigate"
    AVOID = "avoid"
    WAITING = "waiting"
    STOPPED = "stopped"


class WarehouseAGV:
    """Main AGV controller - orchestrates all subsystems."""

    def __init__(self):
        # Subsystems
        self.camera = RealSenseCamera()
        self.motors = MotorController()
        self.odometry = OdometryFusion()
        self.voxel_map = VoxelMap()
        self.obstacle_avoidance = ObstacleAvoidance()
        self.ocr = OCRReader()
        self.semantic_map = SemanticMap()
        self.planner = RemotePlannerClient()

        # State
        self.mode = AGVMode.STOPPED
        self.current_goal: Optional[str] = None
        self.instruction_queue: List[PlannerInstruction] = []
        self.current_instruction: Optional[PlannerInstruction] = None

        # Control flags
        self._running = False
        self._loop_rate = config.MAIN_LOOP_RATE
        self._planner_busy = False

    def initialize(self) -> bool:
        """Initialize all subsystems."""
        print("=" * 50)
        print("  Warehouse AGV - Initializing")
        print("=" * 50)

        # Connect motor controller
        print("\n[1/4] Connecting to Arduino...")
        if not self.motors.connect():
            print("  FAILED: Could not connect to Arduino")
            return False
        print("  OK")

        # Start camera
        print("\n[2/4] Starting RealSense camera...")
        if not self.camera.start():
            print("  FAILED: Could not start camera")
            return False
        print("  OK")

        # Check planner
        print("\n[3/4] Checking remote planner...")
        if self.planner.check_connection():
            print(f"  OK: Planner online at {config.PLANNER_URL}")
        else:
            print(f"  WARNING: Planner not reachable at {config.PLANNER_URL}")
            print("  Robot will operate in local-only mode")

        # Load previous map if available
        print("\n[4/4] Loading previous maps...")
        self.semantic_map.load()
        self.voxel_map.load()
        print("  OK")

        print("\n" + "=" * 50)
        print("  Initialization complete!")
        print("=" * 50)
        return True

    def start_exploration(self):
        """Start exploring the warehouse."""
        self.mode = AGVMode.EXPLORE
        self.current_goal = None
        self.instruction_queue = []
        print("\n[AGV] Mode: EXPLORE - Driving and discovering aisles")

    def navigate_to(self, goal: str):
        """
        Navigate to a specific aisle.
        
        If the aisle is known, requests a plan from the remote planner.
        If unknown, switches to explore mode to find it.
        """
        self.current_goal = goal.upper()
        print(f"\n[AGV] Goal set: Navigate to {self.current_goal}")

        if self.semantic_map.knows_location(self.current_goal):
            # Known location - request plan
            print(f"  {self.current_goal} is known! Requesting route...")
            self._request_navigation_plan()
        else:
            # Unknown - explore to find it
            print(f"  {self.current_goal} not yet discovered. Exploring to find it...")
            self.mode = AGVMode.EXPLORE

    def _request_navigation_plan(self):
        """Request a navigation plan from the remote planner."""
        if not self.planner.connected:
            print("[AGV] Planner offline - cannot navigate")
            self.mode = AGVMode.WAITING
            return

        instructions = self.planner.set_goal(
            goal=self.current_goal,
            semantic_map=self.semantic_map.to_dict(),
            current_position=self.odometry.pose.to_dict()
        )

        if instructions:
            self.instruction_queue = instructions
            self.mode = AGVMode.NAVIGATE
            print(f"[AGV] Route received: {len(instructions)} steps")
            for i, inst in enumerate(instructions):
                print(f"  Step {i + 1}: {inst}")
        else:
            print("[AGV] No route received - exploring instead")
            self.mode = AGVMode.EXPLORE

    def stop(self):
        """Emergency stop."""
        self.motors.stop()
        self.mode = AGVMode.STOPPED
        print("[AGV] STOPPED")

    def run(self):
        """Main control loop."""
        self._running = True
        loop_period = 1.0 / self._loop_rate
        print(f"\n[AGV] Control loop started at {self._loop_rate}Hz")

        try:
            while self._running:
                loop_start = time.time()

                self._control_step()

                # Rate limiting
                elapsed = time.time() - loop_start
                sleep_time = loop_period - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\n[AGV] Interrupted by user")
        finally:
            self.shutdown()

    def _control_step(self):
        """Single iteration of the control loop."""
        # 1. Capture camera frames
        color, depth_raw, depth_m = self.camera.get_frames()
        if color is None:
            return

        # 2. Update odometry
        left_ticks, right_ticks = self.motors.get_odometry()
        pose = self.odometry.update(left_ticks, right_ticks, color, depth_m)

        # 3. Update voxel map
        points = self.camera.depth_to_pointcloud(depth_m)
        if len(points) > 0:
            self.voxel_map.insert_point_cloud(points, pose)

        # 4. Update semantic map breadcrumb
        self.semantic_map.add_breadcrumb(pose)

        # 5. Check for aisle signs (periodic)
        signs = self.ocr.read_signs(color)
        for sign in signs:
            self.semantic_map.add_landmark(sign.label, pose, sign.confidence)
            # Check if we just found our goal
            if self.current_goal and sign.label == self.current_goal:
                print(f"\n[AGV] *** FOUND TARGET: {self.current_goal}! ***")
                self.stop()
                return

        # 6. Obstacle avoidance (always active)
        action, confidence, debug = self.obstacle_avoidance.decide(depth_m)

        # 7. Execute based on mode
        if self.mode == AGVMode.EXPLORE:
            self._explore_step(action, confidence, color, depth_m)
        elif self.mode == AGVMode.NAVIGATE:
            self._navigate_step(action, confidence, color, depth_m)
        elif self.mode == AGVMode.WAITING:
            pass  # Do nothing, waiting for planner
        elif self.mode == AGVMode.STOPPED:
            pass

        # 8. Auto-save maps
        if self.voxel_map.should_save():
            self.voxel_map.save()
            self.semantic_map.save()

    def _explore_step(self, action: AvoidanceAction, confidence: float,
                      color, depth_m):
        """Exploration behavior: drive forward, avoid obstacles, read signs."""
        if action == AvoidanceAction.FORWARD:
            self.motors.forward(config.CRUISE_SPEED)

        elif action == AvoidanceAction.SLOW_FORWARD:
            self.motors.forward(config.SLOW_SPEED)

        elif action == AvoidanceAction.STEER_LEFT:
            self.motors.curve_left(config.SLOW_SPEED, ratio=0.3)

        elif action == AvoidanceAction.STEER_RIGHT:
            self.motors.curve_right(config.SLOW_SPEED, ratio=0.3)

        elif action == AvoidanceAction.STOP:
            self.motors.stop()
            # Try turning to find a new path
            self.motors.turn_right(config.TURN_SPEED)
            time.sleep(0.5)
            self.motors.stop()

        elif action == AvoidanceAction.UNCERTAIN:
            # Escalate to planner
            if not self._planner_busy and self.planner.connected:
                self._escalate_to_planner(color, depth_m, "Uncertain obstacle situation during exploration")
            else:
                # Fallback: just stop briefly
                self.motors.stop()

    def _navigate_step(self, action: AvoidanceAction, confidence: float,
                       color, depth_m):
        """Navigation behavior: follow planner instructions with obstacle avoidance."""
        # Obstacle avoidance overrides navigation
        if action == AvoidanceAction.STOP:
            self.motors.stop()
            return
        elif action == AvoidanceAction.UNCERTAIN:
            self.motors.stop()
            if not self._planner_busy and self.planner.connected:
                self._escalate_to_planner(color, depth_m, "Obstacle while navigating to goal")
            return

        # Get next instruction
        if not self.current_instruction:
            if self.instruction_queue:
                self.current_instruction = self.instruction_queue.pop(0)
                print(f"[AGV] Executing: {self.current_instruction}")
            else:
                # All instructions complete
                print(f"[AGV] Route complete. Checking if at goal...")
                if self.current_goal and self.semantic_map.knows_location(self.current_goal):
                    landmark = self.semantic_map.get_landmark(self.current_goal)
                    dist = self.odometry.pose.distance_to(
                        Pose(landmark.x, landmark.y, 0)
                    )
                    if dist < config.GOAL_REACHED_THRESHOLD:
                        print(f"[AGV] *** ARRIVED AT {self.current_goal}! ***")
                        self.stop()
                    else:
                        print(f"[AGV] Still {dist:.1f}m away. Re-planning...")
                        self._request_navigation_plan()
                else:
                    self.mode = AGVMode.EXPLORE
                return

        # Execute current instruction
        inst = self.current_instruction
        if inst.action == "forward":
            if action in (AvoidanceAction.FORWARD, AvoidanceAction.SLOW_FORWARD):
                speed = config.CRUISE_SPEED if inst.speed == "normal" else config.SLOW_SPEED
                self.motors.forward(speed)
            elif action == AvoidanceAction.STEER_LEFT:
                self.motors.curve_left(config.SLOW_SPEED)
            elif action == AvoidanceAction.STEER_RIGHT:
                self.motors.curve_right(config.SLOW_SPEED)
            # TODO: Track distance traveled and complete instruction when done

        elif inst.action == "turn_left":
            self.motors.turn_left(config.TURN_SPEED)
            # Simple timed turn (should use IMU/encoders for accuracy)
            time.sleep(inst.degrees / 90.0 * 0.8)  # Empirical timing
            self.motors.stop()
            self.current_instruction = None

        elif inst.action == "turn_right":
            self.motors.turn_right(config.TURN_SPEED)
            time.sleep(inst.degrees / 90.0 * 0.8)
            self.motors.stop()
            self.current_instruction = None

        elif inst.action == "stop":
            self.motors.stop()
            self.current_instruction = None

        elif inst.action == "explore":
            # Planner wants us to explore
            self.mode = AGVMode.EXPLORE
            self.current_instruction = None

    def _escalate_to_planner(self, color, depth_m, situation: str):
        """Send current scene to remote planner for help."""
        self._planner_busy = True
        self.motors.stop()

        def _async_request():
            try:
                image_bytes = self.camera.get_frame_for_planner(color)
                instructions = self.planner.ask_for_help(
                    image_bytes=image_bytes,
                    semantic_map=self.semantic_map.to_dict(),
                    current_position=self.odometry.pose.to_dict(),
                    situation=situation
                )
                if instructions:
                    self.instruction_queue = instructions
                    self.mode = AGVMode.NAVIGATE
                    print(f"[AGV] Planner help received: {len(instructions)} instructions")
                else:
                    # Fallback: just turn and try again
                    self.motors.turn_right(config.TURN_SPEED)
                    time.sleep(0.5)
                    self.motors.stop()
                    self.mode = AGVMode.EXPLORE
            finally:
                self._planner_busy = False

        # Run planner request in background to not block control loop
        threading.Thread(target=_async_request, daemon=True).start()

    def shutdown(self):
        """Clean shutdown of all systems."""
        print("\n[AGV] Shutting down...")
        self._running = False
        self.motors.stop()
        self.motors.disconnect()
        self.camera.stop()
        self.voxel_map.save()
        self.semantic_map.save()
        print("[AGV] Shutdown complete")
        print(f"  Final pose: {self.odometry.pose}")
        print(f"  Landmarks discovered: {len(self.semantic_map.landmarks)}")
        print(f"  Voxel map: {self.voxel_map.get_stats()}")


# --- Entry Point ---
if __name__ == "__main__":
    import sys

    agv = WarehouseAGV()

    if not agv.initialize():
        print("\nFailed to initialize. Check connections and try again.")
        sys.exit(1)

    # Check for goal from command line
    if len(sys.argv) > 1:
        goal = sys.argv[1]
        print(f"\nGoal provided: {goal}")
        agv.navigate_to(goal)
    else:
        print("\nNo goal provided. Starting in exploration mode.")
        print("Usage: python main.py H4  (to navigate to aisle H4)")
        agv.start_exploration()

    # Run main loop
    agv.run()
