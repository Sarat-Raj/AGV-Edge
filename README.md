```
                                                                                
    W A R E H O U S E   A G V                                                  
                                                                                
    Autonomous Guided Vehicle with Vision-Language Navigation                    
                                                                                
                                                                                
         ._______________________________.                                      
         |  ___   ___   ___   ___   ___  |                                      
         | | H1| | H2| | H3| | H4| | H5| |                                      
         | |___| |___| |___| |___| |___| |                                      
         |   .       R>          *       |                                      
         |   .    .../.......    .       |                                      
         |   .   .          .   .       |                                      
         |   .  .    AGV    .   .       |                                      
         |   . .   finds    .  .       |                                      
         |   ..   its way   . .        |                                      
         |   .       here -->.         |                                      
         |_____________________________|                                      
                                                                                
                                                                                
```

---

## What is this?

A small robot that navigates warehouse aisles by reading signs,
building a map as it goes, and taking natural language commands.

No pre-mapping. No QR codes. No magnetic strips.

Just a camera, some wheels, and a conversation with an LLM.

---

## How it works

```
                                         
  +----------+    USB    +----------+    Serial    +-----------+
  | RealSense|--------->| Jetson   |------------>| Arduino   |
  | D435     |          | Nano     |             | Uno       |
  | (camera) |          | (brain)  |             | (muscles) |
  +----------+          +-----+----+             +-----+-----+
                              |                        |
                              | WiFi                   | PWM
                              v                        v
                        +----------+             +----------+
                        | MacBook  |             | Motors + |
                        | (VLM+LLM|             | Encoders |
                        |  planner)|             +----------+
                        +----------+
                                         
```

**On the robot (Jetson Nano) -- fast, local, always running:**

```
  Camera frame --> Depth analysis --> Obstacle? --> Steer around
                |
                +--> OCR ----------> Read sign --> Tag on map
                |
                +--> Features -----> Track motion --> Update position
                |
                +--> Voxels -------> Build 3D grid --> Sparse map
```

**On the laptop (MacBook) -- slow, smart, called when needed:**

```
  Image -------> MoondreamV2 -----> "Shelves on both sides,
                   (VLM)             clear path ahead,
                                     sign reads H3"
                                          |
                                          v
  Map + Pose --> Phi-3 Mini -------> [turn_right, 90 degrees]
                   (LLM)             [forward, 3.0 meters]
                                     [reason: "H4 is to the right"]
```

---

## The map grows as the robot explores

```
+------------------------------------------------------------+
|                                                            |
|                ############################################|
|                                                            |
|                    ........................................|
|                    ........................................|
|                    ....*H2...R>....*H3.........!H4.........|
|                    ........................................|
|                    ........................................|
|                                                            |
|                ############################################|
|                                                            |
+------------------------------------------------------------+
 Pos:(1.5,0.0) Hdg:0  Voxels:890 Signs:3 GOAL:H4

 #  = wall/shelf
 .  = explored free space
 R> = robot + heading
 *  = discovered aisle sign
 !  = navigation goal
    = unknown (not yet explored)
```

---

## Tell it where to go

```
$ python jetson/main.py H4

[AGV] Goal set: Navigate to H4
[AGV] H4 not yet discovered. Exploring to find it...
[AGV] Mode: EXPLORE
[OCR] Detected: AisleSign('H2', conf=0.91)
[SemanticMap] Discovered: Landmark('H2' @ (0.00, 0.00))
[OCR] Detected: AisleSign('H3', conf=0.88)
[SemanticMap] Discovered: Landmark('H3' @ (3.10, 0.05))
[AGV] Planner: "H4 should be ~3m to the right of H3"
[OCR] Detected: AisleSign('H4', conf=0.93)
[AGV] *** FOUND TARGET: H4! ***
```

---

## Architecture

```
warehouse-agv/
|
|-- firmware/
|   +-- arduino_motor_control/      Motor + encoder + servo control
|
|-- jetson/
|   |-- main.py                     Main control loop (10 Hz)
|   |-- camera.py                   RealSense RGB + depth capture
|   |-- odometry.py                 Encoder + visual odometry fusion
|   |-- mapping.py                  OctoMap-style voxel grid
|   |-- obstacle_avoidance.py       Reactive depth-based avoidance
|   |-- ocr_reader.py              Aisle sign reading (EasyOCR)
|   |-- semantic_map.py            Sign-to-position mapping
|   |-- motor_controller.py        Serial interface to Arduino
|   +-- remote_planner_client.py   HTTP client to laptop planner
|
|-- planner/
|   |-- server.py                   FastAPI REST API
|   |-- vlm_service.py             MoondreamV2 via Ollama
|   |-- llm_service.py             Phi-3 Mini via Ollama
|   +-- prompts.py                 System prompts for planning
|
|-- visualization/
|   |-- map_visualizer.py          Live ASCII + image map renderer
|   |-- dashboard.py               Web dashboard (WebSocket)
|   |-- dashboard_client.py        Jetson state streamer
|   +-- troubleshooting_guide.md   Field debugging reference
|
|-- docs/
|   |-- academic_report.md         Full project report
|   |-- deployment_options.md      Laptop / Server / Cloud setup
|   +-- future_work.md            Voice interaction, multi-robot
|
+-- tests/
    |-- test_obstacle_avoidance.py
    |-- test_semantic_map.py
    |-- test_odometry.py
    +-- test_planner_api.py
```

---

## Hardware

```
+------------------------------------------------------+
| Component            | Model              | Purpose  |
|----------------------|--------------------|----------|
| Compute              | Jetson Nano 4GB    | Brain    |
| Microcontroller      | Arduino Uno        | Muscles  |
| Camera               | RealSense D435     | Eyes     |
| Motor Driver         | L298N H-Bridge     | Power    |
| Motors               | DC + Encoders (x2) | Wheels   |
| Servo                | SG90               | Neck     |
| Remote Brain         | MacBook + Ollama   | Planner  |
+------------------------------------------------------+

Total cost: ~$250-300 (reusing existing hardware)
```

---

## Quick start

**Laptop (planner):**

```
brew install ollama
ollama pull moondream
ollama pull phi3:mini

cd planner/
pip install -r requirements.txt
python server.py
```

**Jetson Nano (robot):**

```
pip install pyrealsense2 opencv-python easyocr pyserial requests numpy
nano jetson/config.py   # set PLANNER_HOST to your laptop IP
python jetson/main.py
```

**Arduino:**

```
Upload firmware/arduino_motor_control/arduino_motor_control.ino
via Arduino IDE or PlatformIO
```

---

## Design decisions

```
Problem                          --> Solution
------------------------------------------------------------------
Pre-mapping is tedious           --> Zero-setup: explore + read signs
LLMs are too slow for safety     --> Hybrid: local avoidance + remote planning
Jetson Nano has 4GB RAM          --> Sparse voxels, not point clouds
Need to know "where am I"       --> OCR anchors + odometry fusion
WiFi might drop                  --> Robot stays safe without planner
Full SLAM is heavy               --> Voxel grid + sign-based semantics
```

---

## What the LLM actually does

It does NOT control the motors directly.

It receives a text description of the world and responds with a plan:

```
INPUT:
  "You are at position (0.0, 0.0) facing right.
   Known landmarks: H2 at (0,0), H3 at (3.1, 0), H4 at (6.0, 0).
   H4 is 6 meters to your right.
   Goal: reach H4."

OUTPUT:
  [{"action": "forward", "distance": 6.0, "reason": "H4 is straight ahead"}]
```

The robot executes this while still running local obstacle avoidance.
If something blocks the path, it asks the LLM again with updated context.

---

## Future work

- Voice commands from humans ("pass on my left")
- Multi-robot map sharing
- Loop closure for drift correction
- Warehouse management system integration

---

## License

MIT

---

```
                                                                    
        "Go to H4"                                                  
              |                                                      
              v                                                      
   +-------------------+                                            
   |     [ PLAN ]      |     "H4 is 6m ahead"                      
   |  Phi-3 Mini LLM   |---------------------------+               
   +-------------------+                           |               
                                                    v               
                                              +----------+          
                                              |   [GO]   |          
                                              |  R ...>  |          
                                              |  ------> |          
                                              | *H4      |          
                                              +----------+          
                                                                    
   Built with:                                                      
   - A camera that sees depth                                       
   - A model that reads signs                                       
   - A model that makes plans                                       
   - And wheels that follow through                                 
                                                                    
```
