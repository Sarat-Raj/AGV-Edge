# Field Troubleshooting Guide — Debugging Without AI

A systematic reference for diagnosing and fixing issues on the AGV in the field, organized by symptom.

**Philosophy:** Every bug has a signal. Learn to read the signals.

---

## Quick Diagnostic Checklist

Before diving into specifics, always check these first:

```
□ Power: Are all LEDs on? Battery voltage OK?
□ Connections: USB cables seated? Serial connected?
□ WiFi: Can Jetson ping the MacBook?
□ Processes: Is main.py running? Is the planner server up?
□ Logs: What's the last line in the terminal output?
```

---

## Section 1: Motors & Movement

### Symptom: Robot doesn't move at all

| Check | How | Fix |
|-------|-----|-----|
| Arduino getting power? | Check power LED on Arduino | Reconnect USB or check 5V supply |
| Serial connected? | `ls /dev/ttyACM*` on Jetson | Replug USB, check port in config.py |
| Arduino firmware running? | Open Serial Monitor at 115200, look for `{"type":"ready"}` | Re-upload firmware |
| Motor power supply? | Measure battery voltage with multimeter (should be 7-12V) | Charge/replace battery |
| L298N enable jumpers? | Check ENA/ENB pins have jumpers or PWM wires | Add jumpers or connect PWM wires |
| Motor wires? | Swap motor wires and test | Resolder loose connections |

**Debug command (run on Jetson):**
```python
python -c "
from motor_controller import MotorController
mc = MotorController()
mc.connect()
mc.forward(150)
import time; time.sleep(2)
mc.stop()
mc.disconnect()
"
```

### Symptom: Robot moves but drifts left/right

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Unequal wheel friction | Lift robot, spin each wheel by hand | Clean wheels, check for hair/debris |
| Different motor speeds | Print encoder ticks for same PWM command | Add software compensation: increase weaker motor PWM by 5-10% |
| Misaligned wheels | Visual inspection from behind | Adjust chassis/motor mount |
| One encoder broken | `mc.get_total_ticks()` — one side always 0 | Check encoder wiring, test with oscilloscope |

### Symptom: Robot jerks/stutters

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Serial buffer overflow | Reduce odometry report rate | Increase `ODOM_REPORT_INTERVAL_MS` in firmware |
| Loose motor connections | Jiggle wires while running | Resolder, add hot glue strain relief |
| PWM too low | Robot stalls at low speed | Increase `SLOW_SPEED` in config.py (min ~60 for most motors) |
| Main loop too slow | Print loop time | Reduce OCR frequency, skip frames |

---

## Section 2: Camera & Perception

### Symptom: "Could not start camera" error

| Check | How | Fix |
|-------|-----|-----|
| USB connected? | `lsusb` — look for "Intel RealSense" | Replug USB3 port (not USB2) |
| Another process using it? | `fuser /dev/video*` | Kill other process or reboot |
| USB power? | RealSense needs 900mA | Use powered USB hub or connect directly to Jetson |
| Driver installed? | `rs-enumerate-devices` | Reinstall librealsense |

**Debug command:**
```bash
# Test camera directly
rs-enumerate-devices    # Should list your camera
realsense-viewer        # GUI viewer (if display available)

# Python test
python -c "
import pyrealsense2 as rs
pipe = rs.pipeline()
pipe.start()
frames = pipe.wait_for_frames()
print(f'Got frame: {frames.get_depth_frame().get_width()}x{frames.get_depth_frame().get_height()}')
pipe.stop()
"
```

### Symptom: Depth data is noisy/invalid (lots of zeros)

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Too close to surface | Check minimum range (D435 = 0.1m) | Back up the robot |
| Reflective surfaces | Shiny floors, metal shelves | Angle camera slightly down |
| Direct sunlight/IR interference | Test in different lighting | Add IR filter or work indoors |
| Camera warming up | First 30 frames are unstable | Already handled (warmup in camera.py) |

### Symptom: OCR not reading signs

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Too far from sign | Check sign distance (need <2m) | Drive closer before reading |
| Poor lighting | Test with phone flashlight on sign | Add LED light to robot |
| Sign font too small | Print test sign, measure | Use larger font (72pt+ bold) |
| Wrong angle | Camera not facing sign squarely | Pan servo to face sign |
| OCR model issue | Test with synthetic image (see ocr_reader.py main) | Try PaddleOCR instead of EasyOCR |

**Debug command:**
```python
python -c "
from camera import RealSenseCamera
from ocr_reader import OCRReader
import cv2

cam = RealSenseCamera()
cam.start()
color, _, _ = cam.get_frames()
cv2.imwrite('/tmp/test_frame.jpg', color)
print('Saved frame to /tmp/test_frame.jpg — check if sign is visible and clear')

ocr = OCRReader()
ocr.last_check_time = 0  # Force immediate check
signs = ocr.read_signs(color)
print(f'Detected signs: {signs}')
cam.stop()
"
```

---

## Section 3: Odometry & Localization

### Symptom: Position drifts badly over short distances

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Wheel slip | Drive on dusty/smooth floor | Add rubber bands to wheels, clean floor |
| Wrong METERS_PER_TICK | Measure: drive 1m, count ticks, calculate | Update config.py with measured value |
| Wrong WHEEL_BASE | Measure actual wheel-to-wheel distance | Update config.py |
| Encoder miscounting | Drive 1 wheel revolution, check tick count vs expected | Check encoder disk, clean sensor |

**Calibration procedure:**
```python
# Step 1: Calibrate METERS_PER_TICK
# Mark start line on floor. Drive forward until 1000 ticks. Measure actual distance.
# METERS_PER_TICK = measured_distance / 1000

# Step 2: Calibrate WHEEL_BASE
# Command a 360-degree spin (left=-100, right=100) for N ticks
# If robot over-rotates: WHEEL_BASE is too small, increase it
# If robot under-rotates: WHEEL_BASE is too large, decrease it
```

### Symptom: Visual odometry returns None frequently

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Featureless environment | Blank walls, uniform floor | Add visual features (tape, posters) or rely on encoders |
| Moving too fast | Motion blur | Reduce speed or increase camera FPS |
| Low light | Dark warehouse | Add lighting |
| ORB detector finding <10 features | Print keypoint count | Increase `nfeatures` in VisualOdometry init |

---

## Section 4: Obstacle Avoidance

### Symptom: Robot stops when nothing is there (false positives)

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Floor detected as obstacle | Print depth values in center zone | Raise `v_start` in obstacle_avoidance.py to ignore lower image |
| Depth noise spikes | Log min distances per frame | Add median filter on depth before deciding |
| Threshold too sensitive | Obstacles >0.5m triggering stop | Increase `OBSTACLE_STOP_DISTANCE` |

### Symptom: Robot hits obstacles (false negatives)

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Thin objects (legs, poles) | Test with narrow obstacle | Decrease depth zone threshold or use smaller zones |
| Obstacle above/below camera FOV | Check object is within 30%-80% of image height | Tilt camera or adjust `v_start`/`v_end` |
| Processing too slow | Robot moves between frames | Reduce speed near obstacles |
| Glass/transparent objects | RealSense can't see glass | Add ultrasonic sensor as backup |

**Debug command:**
```python
python -c "
from camera import RealSenseCamera
from obstacle_avoidance import ObstacleAvoidance
import numpy as np

cam = RealSenseCamera()
cam.start()
oa = ObstacleAvoidance()

for i in range(10):
    _, _, depth = cam.get_frames()
    action, conf, debug = oa.decide(depth)
    print(f'Frame {i}: {action.value} (conf={conf:.2f}) L={debug[\"left\"][\"min\"]:.2f}m C={debug[\"center\"][\"min\"]:.2f}m R={debug[\"right\"][\"min\"]:.2f}m')
    import time; time.sleep(0.5)
cam.stop()
"
```

---

## Section 5: Network & Remote Planner

### Symptom: Planner timeout / connection refused

| Check | How | Fix |
|-------|-----|-----|
| MacBook IP correct? | `ping <PLANNER_HOST>` from Jetson | Update config.py with current IP |
| Planner server running? | Check MacBook terminal | `cd planner && python server.py` |
| Firewall blocking? | `curl http://<IP>:8000/health` from Jetson | Allow port 8000 in macOS firewall |
| Same WiFi network? | Check both devices' network name | Connect to same network |
| Ollama running? | On MacBook: `curl http://localhost:11434/api/tags` | Start with `ollama serve` |

### Symptom: Planner responds but gives bad instructions

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Bad prompt | Read `reasoning` field in response | Tweak prompts in prompts.py |
| Semantic map empty | Check map has landmarks | Explore more before asking for navigation |
| Image too dark/blurry | Save planner input image, inspect | Improve lighting, reduce image compression |
| Model hallucinating | LLM suggests impossible distances | Add max-distance cap in instruction parsing |

---

## Section 6: System-Level Issues

### Symptom: Jetson Nano overheating / throttling

| Sign | Diagnosis | Fix |
|------|-----------|-----|
| Performance drops after minutes | `cat /sys/devices/virtual/thermal/thermal_zone*/temp` (>80000 = hot) | Add heatsink + fan |
| Kernel messages about throttling | `dmesg | grep -i therm` | Reduce workload: lower camera FPS, skip OCR frames |
| Sudden shutdown | Overtemp protection | Must add cooling, non-negotiable |

### Symptom: Out of memory crashes

| Sign | Diagnosis | Fix |
|------|-----------|-----|
| Process killed randomly | `dmesg | grep -i "out of memory"` | Reduce PROCESS_WIDTH/HEIGHT, limit voxel map size |
| Swap thrashing | `free -m` shows swap used heavily | Add swap file: `sudo fallocate -l 4G /swapfile` |
| Memory grows over time | `top` or `htop` — watch RSS | Cap exploration_path length, prune old voxels |

### Symptom: Main loop running too slow (<10 Hz)

| Bottleneck | Diagnosis | Fix |
|------------|-----------|-----|
| OCR taking too long | Time the `ocr.read_signs()` call | Increase `OCR_CHECK_INTERVAL` to 2-3s |
| Voxel insertion slow | Time `voxel_map.insert_point_cloud()` | Increase subsampling step, reduce max points |
| Visual odometry slow | Time `visual_odom.update()` | Reduce ORB features from 500 to 200 |
| Serial blocking | Time motor commands | Ensure non-blocking reads in background thread |

**Profiling:**
```python
import time

t0 = time.time()
color, _, depth = camera.get_frames()
t1 = time.time()
pose = odometry.update(ticks_l, ticks_r, color, depth)
t2 = time.time()
voxel_map.insert_point_cloud(points, pose)
t3 = time.time()
action, _, _ = obstacle_avoidance.decide(depth)
t4 = time.time()

print(f"Camera: {(t1-t0)*1000:.0f}ms | Odom: {(t2-t1)*1000:.0f}ms | "
      f"Voxel: {(t3-t2)*1000:.0f}ms | Avoid: {(t4-t3)*1000:.0f}ms | "
      f"Total: {(t4-t0)*1000:.0f}ms")
```

---

## Section 7: General Debugging Methodology

When you hit a bug you've never seen before:

### Step 1: Isolate the layer
```
Physical → Arduino → Serial → Jetson Software → WiFi → Planner
```
Which layer is broken? Test each independently.

### Step 2: Reproduce minimally
Don't debug the full system. Write a 10-line script that triggers just the broken part.

### Step 3: Read the actual values
Don't guess. Print the actual numbers:
- What depth value is the sensor returning?
- What PWM is being sent to the motors?
- What ticks are the encoders reporting?
- What did the LLM actually respond with?

### Step 4: Change one thing at a time
If you change 3 things and it works, you don't know which one fixed it. You'll hit the bug again.

### Step 5: Write it down
Keep a `debug_log.txt` in the project. Future-you will thank present-you.

---

## Essential Tools

| Tool | What for | Install |
|------|----------|---------|
| `multimeter` | Check voltages, motor current | Physical tool |
| `htop` | CPU/memory monitoring | `sudo apt install htop` |
| `screen` / `minicom` | Raw serial debugging | `sudo apt install screen` |
| `rs-enumerate-devices` | RealSense diagnostics | Comes with librealsense |
| `cv2.imwrite()` | Save frames to inspect later | Already installed |
| Oscilloscope (optional) | Debug encoder signals, PWM timing | Physical tool |
| `tcpdump` / `wireshark` | Network debugging | `sudo apt install tcpdump` |

---

## Common "It worked yesterday" causes

1. **IP address changed** — MacBook got new DHCP address → update config.py
2. **Battery dying** — Voltage drops → motors weak → encoders miscount → odometry drifts
3. **USB loose** — Vibration loosened RealSense/Arduino cable
4. **Ollama model unloaded** — MacBook slept, Ollama needs to reload model (first request slow)
5. **SD card corruption** — Jetson Nano's microSD corrupted from hard power-off → always shut down cleanly

---

## The #1 Rule

> **If you can't explain WHY something broke, you haven't fixed it — you've just gotten lucky.**

Measure. Hypothesize. Test. Confirm.
