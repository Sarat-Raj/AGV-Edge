"""
Warehouse AGV - Configuration Constants

All tunable parameters for the AGV system.
Adjust these based on your specific hardware and environment.
"""

# --- Serial Communication ---
ARDUINO_PORT = "/dev/ttyACM0"  # USB serial to Arduino
ARDUINO_BAUD = 115200
SERIAL_TIMEOUT = 0.1  # seconds

# --- RealSense Camera ---
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 15
# Downscaled resolution for processing
PROCESS_WIDTH = 320
PROCESS_HEIGHT = 240

# --- Motor Control ---
# PWM values (0-255)
MAX_SPEED = 180
CRUISE_SPEED = 120
TURN_SPEED = 100
SLOW_SPEED = 80

# --- Differential Drive Parameters ---
WHEEL_BASE = 0.20  # meters - distance between wheels
WHEEL_RADIUS = 0.033  # meters - wheel radius
ENCODER_TICKS_PER_REV = 360  # encoder resolution
# Meters per encoder tick
METERS_PER_TICK = (2 * 3.14159 * WHEEL_RADIUS) / ENCODER_TICKS_PER_REV

# --- Obstacle Avoidance ---
# Depth zones (in meters)
OBSTACLE_STOP_DISTANCE = 0.40  # Stop if obstacle within this distance
OBSTACLE_SLOW_DISTANCE = 0.80  # Slow down within this distance
OBSTACLE_CLEAR_DISTANCE = 1.20  # All clear beyond this

# Zone widths (fraction of image width)
CENTER_ZONE_WIDTH = 0.4  # Middle 40% of image
SIDE_ZONE_WIDTH = 0.3  # Each side 30% of image

# Confidence threshold - below this, escalate to remote planner
AVOIDANCE_CONFIDENCE_THRESHOLD = 0.6

# --- OctoMap ---
OCTOMAP_RESOLUTION = 0.05  # meters (5cm voxels)
OCTOMAP_MAX_RANGE = 4.0  # meters - max depth to insert
OCTOMAP_SAVE_INTERVAL = 30  # seconds - auto-save interval
OCTOMAP_FILE = "warehouse_map.bt"

# --- OCR ---
OCR_CONFIDENCE_THRESHOLD = 0.5
OCR_CHECK_INTERVAL = 1.0  # seconds - how often to check for signs
# Regex pattern for aisle labels (e.g., H4, J12, A1)
AISLE_LABEL_PATTERN = r"^[A-Z]\d{1,2}$"

# --- Odometry Fusion ---
# Complementary filter weights (encoder vs visual)
ENCODER_WEIGHT = 0.7
VISUAL_ODOM_WEIGHT = 0.3

# --- Remote Planner ---
PLANNER_HOST = "192.168.1.100"  # MacBook IP on local WiFi
PLANNER_PORT = 8000
PLANNER_URL = f"http://{PLANNER_HOST}:{PLANNER_PORT}"
PLANNER_TIMEOUT = 10  # seconds
PLANNER_RETRY_COUNT = 2

# Image sent to planner (further downscaled to reduce network load)
PLANNER_IMAGE_WIDTH = 160
PLANNER_IMAGE_HEIGHT = 120
PLANNER_IMAGE_QUALITY = 60  # JPEG quality

# --- Semantic Map ---
SEMANTIC_MAP_FILE = "semantic_map.json"

# --- Navigation ---
GOAL_REACHED_THRESHOLD = 0.30  # meters - consider goal reached within this distance
HEADING_TOLERANCE = 0.15  # radians (~8.6 degrees)

# --- System ---
MAIN_LOOP_RATE = 10  # Hz - main control loop frequency
LOG_LEVEL = "INFO"
