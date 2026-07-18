"""
Warehouse AGV - Motor Controller Interface

Handles serial communication with Arduino for motor control and encoder reading.
"""

import json
import time
import threading
import serial
from typing import Optional, Dict, Tuple

import config


class MotorController:
    """Interface to Arduino motor controller over serial."""

    def __init__(self, port: str = config.ARDUINO_PORT, baud: int = config.ARDUINO_BAUD):
        self.port = port
        self.baud = baud
        self.serial: Optional[serial.Serial] = None
        self.connected = False

        # Latest odometry data
        self.left_ticks = 0
        self.right_ticks = 0
        self.left_total = 0
        self.right_total = 0
        self._odom_lock = threading.Lock()

        # Background reader thread
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False

    def connect(self) -> bool:
        """Establish serial connection to Arduino."""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=config.SERIAL_TIMEOUT
            )
            time.sleep(2)  # Wait for Arduino reset after serial connection

            # Wait for ready message
            deadline = time.time() + 5.0
            while time.time() < deadline:
                line = self.serial.readline().decode('utf-8').strip()
                if line:
                    try:
                        msg = json.loads(line)
                        if msg.get("type") == "ready":
                            print(f"[MotorController] Connected: {msg.get('firmware')}")
                            self.connected = True
                            self._start_reader()
                            return True
                    except json.JSONDecodeError:
                        continue

            print("[MotorController] ERROR: No ready message from Arduino")
            return False

        except serial.SerialException as e:
            print(f"[MotorController] ERROR: {e}")
            return False

    def disconnect(self):
        """Clean shutdown."""
        self._running = False
        if self._reader_thread:
            self._reader_thread.join(timeout=2.0)
        self.stop()
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.connected = False
        print("[MotorController] Disconnected")

    def _start_reader(self):
        """Start background thread to read serial responses."""
        self._running = True
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def _reader_loop(self):
        """Background loop reading serial data from Arduino."""
        while self._running:
            try:
                if self.serial and self.serial.in_waiting:
                    line = self.serial.readline().decode('utf-8').strip()
                    if line:
                        self._process_response(line)
                else:
                    time.sleep(0.01)
            except (serial.SerialException, OSError):
                self._running = False
                self.connected = False
                break

    def _process_response(self, line: str):
        """Parse and handle a response from Arduino."""
        try:
            msg = json.loads(line)
            msg_type = msg.get("type")

            if msg_type == "odom":
                with self._odom_lock:
                    self.left_ticks = msg.get("left", 0)
                    self.right_ticks = msg.get("right", 0)
                    self.left_total = msg.get("left_total", 0)
                    self.right_total = msg.get("right_total", 0)

            elif msg_type == "error":
                print(f"[MotorController] Arduino error: {msg.get('msg')}")

            elif msg_type == "ack":
                pass  # Command acknowledged

        except json.JSONDecodeError:
            pass  # Ignore malformed messages

    def _send_command(self, cmd: Dict) -> bool:
        """Send a JSON command to Arduino."""
        if not self.connected or not self.serial:
            print("[MotorController] Not connected")
            return False

        try:
            msg = json.dumps(cmd) + "\n"
            self.serial.write(msg.encode('utf-8'))
            return True
        except serial.SerialException as e:
            print(f"[MotorController] Send error: {e}")
            return False

    # --- Public Motor Commands ---

    def move(self, left_pwm: int, right_pwm: int) -> bool:
        """Set motor PWM values. Range: -255 to 255."""
        left_pwm = max(-255, min(255, int(left_pwm)))
        right_pwm = max(-255, min(255, int(right_pwm)))
        return self._send_command({"cmd": "move", "left": left_pwm, "right": right_pwm})

    def stop(self) -> bool:
        """Emergency stop both motors."""
        return self._send_command({"cmd": "stop"})

    def forward(self, speed: int = config.CRUISE_SPEED) -> bool:
        """Drive straight forward."""
        return self.move(speed, speed)

    def backward(self, speed: int = config.CRUISE_SPEED) -> bool:
        """Drive straight backward."""
        return self.move(-speed, -speed)

    def turn_left(self, speed: int = config.TURN_SPEED) -> bool:
        """Turn left in place."""
        return self.move(-speed, speed)

    def turn_right(self, speed: int = config.TURN_SPEED) -> bool:
        """Turn right in place."""
        return self.move(speed, -speed)

    def curve_left(self, speed: int = config.CRUISE_SPEED, ratio: float = 0.5) -> bool:
        """Curve to the left while moving forward."""
        return self.move(int(speed * ratio), speed)

    def curve_right(self, speed: int = config.CRUISE_SPEED, ratio: float = 0.5) -> bool:
        """Curve to the right while moving forward."""
        return self.move(speed, int(speed * ratio))

    # --- Servo ---

    def set_servo(self, angle: int) -> bool:
        """Set camera servo angle (0-180 degrees). 90 = center."""
        angle = max(0, min(180, int(angle)))
        return self._send_command({"cmd": "servo", "angle": angle})

    # --- Odometry ---

    def get_odometry(self) -> Tuple[int, int]:
        """Get latest encoder tick deltas (left, right) since last report."""
        with self._odom_lock:
            return self.left_ticks, self.right_ticks

    def get_total_ticks(self) -> Tuple[int, int]:
        """Get total accumulated encoder ticks."""
        with self._odom_lock:
            return self.left_total, self.right_total

    def reset_odometry(self) -> bool:
        """Reset encoder counters to zero."""
        return self._send_command({"cmd": "reset_odom"})


# --- Quick test ---
if __name__ == "__main__":
    mc = MotorController()
    if mc.connect():
        print("Moving forward for 2 seconds...")
        mc.forward(100)
        time.sleep(2)
        mc.stop()
        time.sleep(0.5)
        left, right = mc.get_total_ticks()
        print(f"Encoder totals: left={left}, right={right}")
        mc.disconnect()
    else:
        print("Failed to connect to Arduino")
