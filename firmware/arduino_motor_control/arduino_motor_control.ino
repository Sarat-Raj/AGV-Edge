/*
 * Warehouse AGV - Arduino Motor Controller Firmware
 * 
 * Receives JSON commands via Serial from Jetson Nano.
 * Controls: 2x DC motors (differential drive) + 1x servo (camera pan)
 * Reports: Encoder ticks for odometry
 * 
 * Serial Protocol (115200 baud):
 *   Commands (JSON from Jetson):
 *     {"cmd": "move", "left": 150, "right": 150}     // PWM values -255 to 255
 *     {"cmd": "stop"}                                  // Emergency stop
 *     {"cmd": "servo", "angle": 90}                   // Servo angle 0-180
 *     {"cmd": "odom"}                                  // Request encoder counts
 *   
 *   Responses (JSON to Jetson):
 *     {"type": "odom", "left": 1234, "right": 1230, "dt_ms": 100}
 *     {"type": "ack", "cmd": "move"}
 *     {"type": "error", "msg": "unknown command"}
 * 
 * Wiring:
 *   Motor A (Left):  ENA=5, IN1=7, IN2=8,  Encoder A=2 (interrupt)
 *   Motor B (Right): ENB=6, IN3=9, IN4=10, Encoder B=3 (interrupt)
 *   Servo: Pin 11
 */

#include <Servo.h>
#include <ArduinoJson.h>

// --- Pin Definitions ---
// Motor A (Left)
#define ENA 5
#define IN1 7
#define IN2 8
#define ENCODER_A 2  // Interrupt pin

// Motor B (Right)
#define ENB 6
#define IN3 9
#define IN4 10
#define ENCODER_B 3  // Interrupt pin

// Servo
#define SERVO_PIN 11

// --- Constants ---
#define SERIAL_BAUD 115200
#define ODOM_REPORT_INTERVAL_MS 100  // Auto-report odometry every 100ms
#define WATCHDOG_TIMEOUT_MS 1000     // Stop motors if no command for 1s
#define JSON_BUFFER_SIZE 256

// --- Global State ---
Servo cameraServo;

// Encoder counts (volatile for ISR access)
volatile long encoderLeftCount = 0;
volatile long encoderRightCount = 0;

// Previous counts for delta reporting
long prevLeftCount = 0;
long prevRightCount = 0;

// Timing
unsigned long lastOdomReport = 0;
unsigned long lastCommandTime = 0;

// Current motor state
int currentLeftPWM = 0;
int currentRightPWM = 0;

// Serial input buffer
String inputBuffer = "";
bool inputComplete = false;

// --- Encoder ISRs ---
void encoderLeftISR() {
    // Simple counting - direction determined by motor command sign
    if (currentLeftPWM >= 0) {
        encoderLeftCount++;
    } else {
        encoderLeftCount--;
    }
}

void encoderRightISR() {
    if (currentRightPWM >= 0) {
        encoderRightCount++;
    } else {
        encoderRightCount--;
    }
}

// --- Motor Control ---
void setMotorLeft(int pwm) {
    currentLeftPWM = pwm;
    if (pwm > 0) {
        digitalWrite(IN1, HIGH);
        digitalWrite(IN2, LOW);
        analogWrite(ENA, min(pwm, 255));
    } else if (pwm < 0) {
        digitalWrite(IN1, LOW);
        digitalWrite(IN2, HIGH);
        analogWrite(ENA, min(-pwm, 255));
    } else {
        digitalWrite(IN1, LOW);
        digitalWrite(IN2, LOW);
        analogWrite(ENA, 0);
    }
}

void setMotorRight(int pwm) {
    currentRightPWM = pwm;
    if (pwm > 0) {
        digitalWrite(IN3, HIGH);
        digitalWrite(IN4, LOW);
        analogWrite(ENB, min(pwm, 255));
    } else if (pwm < 0) {
        digitalWrite(IN3, LOW);
        digitalWrite(IN4, HIGH);
        analogWrite(ENB, min(-pwm, 255));
    } else {
        digitalWrite(IN3, LOW);
        digitalWrite(IN4, LOW);
        analogWrite(ENB, 0);
    }
}

void stopMotors() {
    setMotorLeft(0);
    setMotorRight(0);
}

// --- Serial Communication ---
void sendOdometry() {
    long leftDelta = encoderLeftCount - prevLeftCount;
    long rightDelta = encoderRightCount - prevRightCount;
    prevLeftCount = encoderLeftCount;
    prevRightCount = encoderRightCount;

    StaticJsonDocument<JSON_BUFFER_SIZE> doc;
    doc["type"] = "odom";
    doc["left"] = leftDelta;
    doc["right"] = rightDelta;
    doc["left_total"] = encoderLeftCount;
    doc["right_total"] = encoderRightCount;
    doc["dt_ms"] = ODOM_REPORT_INTERVAL_MS;

    serializeJson(doc, Serial);
    Serial.println();
}

void sendAck(const char* cmd) {
    StaticJsonDocument<JSON_BUFFER_SIZE> doc;
    doc["type"] = "ack";
    doc["cmd"] = cmd;
    serializeJson(doc, Serial);
    Serial.println();
}

void sendError(const char* msg) {
    StaticJsonDocument<JSON_BUFFER_SIZE> doc;
    doc["type"] = "error";
    doc["msg"] = msg;
    serializeJson(doc, Serial);
    Serial.println();
}

// --- Command Processing ---
void processCommand(String& json) {
    StaticJsonDocument<JSON_BUFFER_SIZE> doc;
    DeserializationError error = deserializeJson(doc, json);

    if (error) {
        sendError("JSON parse error");
        return;
    }

    const char* cmd = doc["cmd"];
    if (cmd == nullptr) {
        sendError("missing cmd field");
        return;
    }

    lastCommandTime = millis();

    if (strcmp(cmd, "move") == 0) {
        int leftPWM = doc["left"] | 0;
        int rightPWM = doc["right"] | 0;

        // Clamp values
        leftPWM = constrain(leftPWM, -255, 255);
        rightPWM = constrain(rightPWM, -255, 255);

        setMotorLeft(leftPWM);
        setMotorRight(rightPWM);
        sendAck("move");

    } else if (strcmp(cmd, "stop") == 0) {
        stopMotors();
        sendAck("stop");

    } else if (strcmp(cmd, "servo") == 0) {
        int angle = doc["angle"] | 90;
        angle = constrain(angle, 0, 180);
        cameraServo.write(angle);
        sendAck("servo");

    } else if (strcmp(cmd, "odom") == 0) {
        sendOdometry();

    } else if (strcmp(cmd, "reset_odom") == 0) {
        noInterrupts();
        encoderLeftCount = 0;
        encoderRightCount = 0;
        interrupts();
        prevLeftCount = 0;
        prevRightCount = 0;
        sendAck("reset_odom");

    } else {
        sendError("unknown command");
    }
}

// --- Setup ---
void setup() {
    Serial.begin(SERIAL_BAUD);

    // Motor pins
    pinMode(ENA, OUTPUT);
    pinMode(IN1, OUTPUT);
    pinMode(IN2, OUTPUT);
    pinMode(ENB, OUTPUT);
    pinMode(IN3, OUTPUT);
    pinMode(IN4, OUTPUT);

    // Encoder pins
    pinMode(ENCODER_A, INPUT_PULLUP);
    pinMode(ENCODER_B, INPUT_PULLUP);

    // Attach interrupts
    attachInterrupt(digitalPinToInterrupt(ENCODER_A), encoderLeftISR, RISING);
    attachInterrupt(digitalPinToInterrupt(ENCODER_B), encoderRightISR, RISING);

    // Servo
    cameraServo.attach(SERVO_PIN);
    cameraServo.write(90);  // Center position

    // Initialize motors stopped
    stopMotors();

    // Ready signal
    StaticJsonDocument<JSON_BUFFER_SIZE> doc;
    doc["type"] = "ready";
    doc["firmware"] = "warehouse-agv-v1.0";
    serializeJson(doc, Serial);
    Serial.println();
}

// --- Main Loop ---
void loop() {
    // Read serial input
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n') {
            inputComplete = true;
        } else if (c != '\r') {
            inputBuffer += c;
        }
    }

    // Process complete command
    if (inputComplete) {
        if (inputBuffer.length() > 0) {
            processCommand(inputBuffer);
        }
        inputBuffer = "";
        inputComplete = false;
    }

    // Auto-report odometry at fixed interval
    unsigned long now = millis();
    if (now - lastOdomReport >= ODOM_REPORT_INTERVAL_MS) {
        sendOdometry();
        lastOdomReport = now;
    }

    // Watchdog: stop motors if no command received for too long
    if (now - lastCommandTime > WATCHDOG_TIMEOUT_MS && lastCommandTime > 0) {
        if (currentLeftPWM != 0 || currentRightPWM != 0) {
            stopMotors();
            sendError("watchdog timeout - motors stopped");
        }
    }
}
