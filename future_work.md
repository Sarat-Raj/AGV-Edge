# Future Work

This document outlines planned enhancements and features for future iterations of the Warehouse AGV project.

---

## 1. Voice Interaction with Human Obstacles

### Concept
When the AGV encounters a human obstacle, instead of just stopping or blindly avoiding, it listens for voice commands from the person. The human can say things like:
- "Go around me"
- "Pass on my left"
- "Wait here, I'll move"
- "Go back"

### Architecture

```
[Microphone on AGV] → [Wake word detection (local)] → [Speech-to-text (local/remote)]
    → [Intent parsing (LLM)] → [Movement instruction] → [Motor control]
```

### Implementation Plan

**Hardware Addition:**
- USB microphone or I2S MEMS mic (e.g., INMP441) connected to Jetson Nano
- Speaker for AGV responses (optional, "beep" or TTS)

**Software Stack:**
- **Wake word:** Porcupine (Picovoice) — runs locally, low power
- **Speech-to-text:** Whisper.cpp (tiny model on Jetson) or send audio to remote planner
- **Intent parsing:** Add to existing LLM pipeline — extract directional commands

**Workflow:**
1. Obstacle avoidance detects a person (depth + size heuristics)
2. AGV stops and activates microphone listening
3. Wake word detected ("Hey robot" or just any speech above threshold)
4. Speech captured for 3 seconds → transcribed
5. Transcript sent to LLM: "Person said: 'pass on my left'. Robot is facing forward. What should it do?"
6. LLM responds with movement instruction
7. AGV executes while maintaining obstacle avoidance

**Challenges:**
- Warehouse noise (forklifts, conveyors) → need noise cancellation
- Directional ambiguity ("my left" vs "your left") → LLM needs to resolve perspective
- Latency of voice pipeline vs. urgency of the situation
- Multiple people speaking

---

## 2. Map Persistence Across Sessions

### Current Limitation
The semantic map and voxel map are built from scratch each session (though they can be saved/loaded).

### Enhancement
- Save maps with timestamps and version numbers
- On startup, load the most recent map and validate it (check if signs are still where expected)
- Incremental updates — only re-map areas that have changed
- Cloud sync of maps between multiple AGVs

---

## 3. Multi-Robot Coordination

### Concept
Multiple AGVs operating in the same warehouse need to:
- Share discovered map data
- Avoid collisions with each other
- Divide exploration/delivery tasks

### Architecture
- Central coordinator service (runs on the server)
- Each AGV reports position via MQTT/WebSocket
- Coordinator assigns tasks and deconflicts paths
- Shared semantic map updated by all robots

---

## 4. Improved Localization

### Current Limitation
Visual + encoder odometry drifts over time without absolute position corrections.

### Enhancements
- **Loop closure detection:** When the robot revisits a known area, correct accumulated drift
- **IMU fusion:** Add a BNO055 or MPU6050 IMU for better rotation estimation
- **Floor line following:** Use the 5S floor markings as additional localization cues
- **UWB beacons:** Ultra-wideband anchors at known positions for centimeter-level positioning

---

## 5. Open-Vocabulary Object Detection

### Concept
Use models like OWL-ViT or Grounding DINO to detect arbitrary objects without pre-training:
- "person", "forklift", "pallet", "spill", "fire extinguisher"
- Enables richer scene descriptions for the LLM planner

### Implementation
- Run on the remote planner (too heavy for Jetson Nano)
- Send image → get bounding boxes + labels → include in planning context

---

## 6. Integration with Warehouse Management Systems (WMS)

### Concept
Connect the AGV to the warehouse's WMS to:
- Receive pick/delivery tasks automatically
- Know which aisles have which products
- Report task completion
- Get real-time aisle closure information

---

## 7. Safety Enhancements

- **E-stop button:** Physical emergency stop on the robot
- **Bumper sensors:** Touch-based last-resort stop
- **Speed limiting near people:** Reduce speed when humans detected
- **Audible warnings:** Beep when moving, louder when turning
- **Light indicators:** LED strip showing direction and status

---

## 8. Power Management

- Battery level monitoring via Arduino ADC
- Low-battery behavior: return to charging station
- Auto-dock charging station with alignment using camera
- Power budget optimization: reduce camera FPS when stationary

---

## Priority Roadmap

| Priority | Feature | Effort | Impact |
|----------|---------|--------|--------|
| P1 | Map persistence | Low | High |
| P1 | Safety (e-stop, bumper) | Low | Critical |
| P2 | Voice interaction | Medium | High |
| P2 | IMU fusion | Low | Medium |
| P3 | Multi-robot coordination | High | High |
| P3 | WMS integration | Medium | High |
| P4 | Open-vocabulary detection | Medium | Medium |
| P4 | UWB localization | Medium | Medium |
