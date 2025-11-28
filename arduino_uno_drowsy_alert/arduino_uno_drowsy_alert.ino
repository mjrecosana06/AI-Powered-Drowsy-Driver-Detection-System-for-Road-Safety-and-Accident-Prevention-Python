#include <Wire.h>
#include <LiquidCrystal_I2C.h>

const int BUZZER_PIN = 9;
const int GREEN_LED_PIN = 8;
const int RED_LED_PIN = 10;

LiquidCrystal_I2C lcd(0x27, 16, 2);

bool alertState = false;
String serialBuffer = "";
unsigned long lastCommandTime = 0;
unsigned long lastStatusUpdate = 0;
String currentStatus = "WAITING";
String cameraStatus = "NO CAM";
int connectionTimeout = 10000; // 10 seconds timeout

void setup() {
  // Initialize Serial communication at 9600 baud (matches Flask app)
  Serial.begin(9600);
  
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);

  digitalWrite(GREEN_LED_PIN, HIGH);
  digitalWrite(RED_LED_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);

  // Initialize LCD (try init() first, fallback to begin() if needed)
  lcd.init();
  lcd.backlight();
  // Some library versions may need lcd.begin() instead, but init() is standard
  
  // Show startup message
  lcd.clear();
  lcd.setCursor(0,0);
  lcd.print("Server Camera");
  lcd.setCursor(0,1);
  lcd.print("Connecting...");
  
  lastStatusUpdate = millis();
}

void loop() {
  // Read serial commands from Flask app (server camera detection system)
  if (Serial.available() > 0) {
    char incomingByte = Serial.read();
    lastCommandTime = millis();
    
    // Build command string until newline is received
    if (incomingByte != '\n' && incomingByte != '\r') {
      // Prevent buffer overflow (max 64 characters)
      if (serialBuffer.length() < 64) {
        serialBuffer += incomingByte;
      } else {
        // Buffer overflow protection: clear and start fresh
        serialBuffer = "";
      }
    } else {
      // Process complete command
      if (serialBuffer.length() > 0) {
        serialBuffer.trim();
        processCommand(serialBuffer);
      }
      serialBuffer = ""; // Clear buffer for next command
    }
  }

  // Check connection timeout (if no commands received for 10 seconds)
  // Only check timeout if we've received at least one command (lastCommandTime > 0)
  // Note: CAM:ACTIVE heartbeat resets lastCommandTime, so timeout only triggers if heartbeat stops
  if (lastCommandTime > 0 && millis() - lastCommandTime > connectionTimeout) {
    if (currentStatus != "DISCONNECTED") {
      currentStatus = "DISCONNECTED";
      cameraStatus = "NO CONNECTION";
      updateDisplay("Server Camera", "Disconnected!");
      digitalWrite(GREEN_LED_PIN, LOW);
      digitalWrite(RED_LED_PIN, LOW);
      // Reset alert state on disconnect
      alertState = false;
      digitalWrite(BUZZER_PIN, LOW);
    }
  }

  // Update status display every 2 seconds
  if (millis() - lastStatusUpdate > 2000) {
    updateStatusDisplay();
    lastStatusUpdate = millis();
  }

  // If in alert mode, beep the buzzer repeatedly
  if (alertState) {
    static unsigned long buzzerTimer = 0;

    if (millis() - buzzerTimer < 300) {
      digitalWrite(BUZZER_PIN, HIGH);   // Beep ON
    } 
    else if (millis() - buzzerTimer < 600) {
      digitalWrite(BUZZER_PIN, LOW);    // Beep OFF
    } 
    else {
      buzzerTimer = millis();           // Reset cycle
    }
  }
}

void processCommand(String cmd) {
  cmd.trim();
  
  // Handle USER:email|COMMAND format (from Flask app)
  // Extract command part after the pipe character
  int pipeIndex = cmd.indexOf('|');
  if (pipeIndex > 0 && cmd.startsWith("USER:")) {
    // Extract command after the pipe
    String actualCmd = cmd.substring(pipeIndex + 1);
    actualCmd.trim();
    actualCmd.toUpperCase();
    processCommand(actualCmd); // Recursively process the actual command
    return;
  }
  
  cmd.toUpperCase(); // Convert to uppercase for case-insensitive matching
  
  // Handle different command formats
  if (cmd.startsWith("ALERT")) {
    startAlert();
    // Check if command includes reason
    if (cmd.length() > 6) {
      String reason = cmd.substring(6);
      reason.trim();
      cameraStatus = reason;
    } else {
      cameraStatus = "DROWSY";
    }
  } 
  else if (cmd.startsWith("SAFE")) {
    stopAlert();
    cameraStatus = "NORMAL";
  }
  else if (cmd.startsWith("CAM:")) {
    // Camera status update: CAM:ACTIVE or CAM:IDLE
    String camState = cmd.substring(4);
    camState.trim();
    camState.toUpperCase(); // Ensure uppercase for comparison
    if (camState == "ACTIVE") {
      cameraStatus = "ACTIVE";
      currentStatus = "MONITORING";
      lastCommandTime = millis(); // Reset timeout on heartbeat
    } else if (camState == "IDLE") {
      cameraStatus = "IDLE";
      currentStatus = "READY";
    }
  }
  else if (cmd.startsWith("EAR:")) {
    // Eye Aspect Ratio update: EAR:0.25
    String earValue = cmd.substring(4);
    cameraStatus = "EAR:" + earValue;
  }
  else if (cmd.startsWith("STATUS:")) {
    // Custom status: STATUS:MONITORING
    String status = cmd.substring(7);
    status.trim();
    status.toUpperCase(); // Ensure uppercase for consistency
    currentStatus = status;
  }
  else {
    // Unknown command, try basic ALERT/SAFE
    if (cmd == "ALERT") {
      startAlert();
      cameraStatus = "DROWSY";
    } else if (cmd == "SAFE") {
      stopAlert();
      cameraStatus = "NORMAL";
    }
  }
}

void startAlert() {
  alertState = true;
  currentStatus = "ALERT";
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, HIGH);
  
  updateDisplay("ALERT: DROWSY!", "Wake Up!");
}

void stopAlert() {
  alertState = false;
  currentStatus = "SAFE";
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RED_LED_PIN, LOW);
  digitalWrite(GREEN_LED_PIN, HIGH);
  
  updateDisplay("System: Normal", "Status: OK");
}

void updateDisplay(String line1, String line2) {
  lcd.clear();
  lcd.setCursor(0, 0);
  // Truncate if too long (16 chars max)
  if (line1.length() > 16) {
    line1 = line1.substring(0, 16);
  }
  lcd.print(line1);
  
  lcd.setCursor(0, 1);
  if (line2.length() > 16) {
    line2 = line2.substring(0, 16);
  }
  lcd.print(line2);
}

void updateStatusDisplay() {
  // Show rotating status information
  static int displayMode = 0;
  displayMode = (displayMode + 1) % 3;
  
  if (alertState) {
    // Always show alert when active
    updateDisplay("ALERT: DROWSY!", "Wake Up!");
    return;
  }
  
  switch (displayMode) {
    case 0:
      // Show connection status
      updateDisplay("Server Camera", cameraStatus);
      break;
    case 1:
      // Show system status
      updateDisplay("Status:", currentStatus);
      break;
    case 2:
      // Show ready message
      if (currentStatus == "MONITORING") {
        updateDisplay("Monitoring...", "Camera Active");
      } else {
        updateDisplay("System Ready", "Waiting...");
      }
      break;
  }
}