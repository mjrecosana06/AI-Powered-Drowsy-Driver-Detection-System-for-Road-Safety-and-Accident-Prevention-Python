# 🚗 AI-Powered Drowsy Driver Detection System for Road Safety and Accident Prevention

🎬 **Watch the full system demo:** [AI Drowsy Driver Detection Demo](https://youtu.be/if3djOvKyb4)

**Mark Joseph Recosana & Fernando Jose Reeves | BSIT**

An intelligent real-time drowsiness detection system designed to prevent road accidents by monitoring driver alertness using computer vision and facial landmark analysis. The system detects early signs of drowsiness through multiple metrics and provides immediate alerts through visual, audio, and IoT-based notifications.

---

## 📸 Screenshots

### Admin Dashboard
![Admin Page 1](Images/Screenshots/Admin%20Page%201.png)
*Admin dashboard with system overview and driver monitoring*

![Admin Page 2](Images/Screenshots/Admin%20Page%202.png)
*Admin settings and configuration panel*

![Admin Left Live Feed Driver Right Monitoring](Images/Screenshots/Admin%20Left%20Live%20Feed%20Driver%20Right%20Monitoring.png)
*Real-time driver monitoring with live video feed*

![Admin Settings applied to all Drivers](Images/Screenshots/Admin%20Settings%20applied%20to%20all%20Drivers.png)
*Centralized settings management for all drivers*

### Driver Dashboard
![Driver Page](Images/Screenshots/Driver%20Page.png)
*Driver monitoring interface with live metrics*

![Driver Settings](Images/Screenshots/Driver%20Settings.png)
*Driver-specific settings and preferences*

![Driver Live Feed from Admin](Images/Screenshots/Driver%20Live%20Feed%20from%20Admin.png)
*Live camera feed viewable from admin panel*

### Arduino Integration
![Arduino Uno R3 Economy Connection 1](Images/Arduino%20Uno%20R3%20Economy%20Circuits/Arduino%20Uno%20R3%20Economy%20Connection%201.JPG)
*Arduino Uno R3 connection setup*

![Arduino Uno R3 Economy Connection 2](Images/Arduino%20Uno%20R3%20Economy%20Circuits/Arduino%20Uno%20R3%20Economy%20Connection%202.JPG)
*Alternative Arduino connection configuration*

![Breadboard Full Size,Active Buzzer 2pc 220 Resistor 1 Red 1 Green LED](Images/Arduino%20Uno%20R3%20Economy%20Circuits/Breadboard%20Full%20Size,Active%20Buzzer%202pc%20220%20Resistor%201%20Red%201%20Green%20LED.JPG)
*Complete breadboard setup with buzzer, LEDs, and resistors*

![I2C Connection](Images/Arduino%20Uno%20R3%20Economy%20Circuits/I2C%20Connection.JPG)
*I2C LCD connection for status display*

### Arduino Library Setup
![LiquidCrystal](Images/Arduino%20Library%20Manager/LiquidCrystal.png)
*LiquidCrystal library installation*

![LCD-I2C](Images/Arduino%20Library%20Manager/LCD-I2C.png)
*LCD-I2C library for display support*

---

## 🔧 Features

### Core Detection Capabilities
- ✅ **Real-time Drowsiness Detection** using MediaPipe FaceMesh
- ✅ **Multi-Metric Analysis:**
  - **EAR (Eye Aspect Ratio)** - Detects eye closure and blink patterns
  - **MAR (Mouth Aspect Ratio)** - Detects yawning behavior
  - **Head Tilt Detection** - Monitors head position for signs of fatigue
  - **PERCLOS (Percentage of Eyelid Closure)** - Measures prolonged eye closure over time
- ✅ **False Alarm Prevention** - Configurable timer thresholds and consecutive frame requirements
- ✅ **Dual Camera Support:**
  - Server camera (USB webcam)
  - Browser camera (WebRTC)

### User Interface
- ✅ **Admin Dashboard** - Monitor multiple drivers simultaneously
- ✅ **Driver Dashboard** - Real-time metrics and status display
- ✅ **Settings Management** - Customizable detection sensitivity and thresholds
- ✅ **Alert History** - Track and review drowsiness events
- ✅ **Multi-Driver Monitoring** - Support for concurrent driver sessions

### Alert & Notification Systems
- ✅ **Visual Alerts** - Full-screen overlay with acknowledgment
- ✅ **Audio Alerts** - Browser-based alarm sounds
- ✅ **Arduino Integration** - Physical buzzer and LED alerts via USB serial
- ✅ **SMS Notifications** - Twilio integration for emergency alerts
- ✅ **Email Notifications** - SMTP support for alert delivery
- ✅ **Telegram Bot** - Real-time notifications via Telegram API

### IoT & Hardware Integration
- ✅ **Arduino Uno R3 Support** - Serial communication for buzzer/LED control
- ✅ **I2C LCD Display** - Real-time status display on LCD screen
- ✅ **Per-User Arduino Configuration** - Individual settings for each driver
- ✅ **Heartbeat Monitoring** - Maintains connection stability

### Deployment & Accessibility
- ✅ **Cloudflare Tunnel** - Free public access tunneling
- ✅ **ngrok Support** - Alternative tunneling solution
- ✅ **LocalTunnel** - Additional deployment option
- ✅ **Cross-Platform** - Works on Windows, macOS, and Linux

---

## 🖥️ Technologies Used

### Backend
- **Python 3.10+**
- **Flask 3.0.3** - Web framework
- **OpenCV 4.10.0** - Computer vision and image processing
- **MediaPipe 0.10.14** - Facial landmark detection
- **NumPy 1.26.4** - Numerical computations
- **PySerial 3.5** - Arduino serial communication

### Frontend
- **HTML5 / CSS3**
- **JavaScript (Vanilla)**
- **Tailwind CSS** - Utility-first CSS framework
- **Phosphor Icons** - Icon library

### External Services
- **Twilio** - SMS notifications
- **SMTP** - Email notifications
- **Telegram Bot API** - Telegram notifications
- **Google Maps API** - Location services

### Hardware
- **Arduino Uno R3** - IoT alert system
- **I2C LCD Display** - Status display
- **Active Buzzer** - Audio alerts
- **LEDs (Red/Green)** - Visual indicators

---

## 📋 Prerequisites

Before installing, ensure you have:

- **Python 3.10 or higher** installed
- **pip** (Python package manager)
- **Webcam** (USB or built-in camera)
- **Arduino Uno R3** (optional, for IoT alerts)
- **Internet connection** (for deployment and notifications)

### For Arduino Integration (Optional)
- Arduino IDE installed
- USB cable to connect Arduino to computer
- Components:
  - Active Buzzer
  - 2x 220Ω Resistors
  - 1x Red LED
  - 1x Green LED
  - I2C LCD Display (16x2)
  - Breadboard and jumper wires

---

## 🚀 Installation Guide

### 1. Clone the Repository

```bash
git clone https://github.com/mjrecosana06/AI-Drowsy-Driver-Detection.git
cd AI-Drowsy-Driver-Detection
```

### 2. Create and Activate Virtual Environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

**Note for Apple Silicon (M1/M2 Macs):**
The requirements.txt automatically handles MediaPipe installation for Apple Silicon. If you encounter issues, you may need to install `mediapipe-silicon` separately:

```bash
pip install mediapipe-silicon
```

### 4. Set Up Environment Variables (Optional)

Create a `.env` file in the project root for custom configuration:

```env
# Camera Settings
CAMERA_INDEX=0
CAM_WIDTH=640
CAM_HEIGHT=480
CAM_FPS=12
CAM_MIRROR=0
JPEG_QUALITY=60

# Detection Thresholds
EAR_THRESHOLD=0.23
MAR_THRESHOLD=0.65
TILT_THRESHOLD_DEG=18
FRAMES_BELOW_THRESH=12
PERCLOS_THRESHOLD=0.2

# Arduino Settings (Optional)
ARDUINO_PORT=/dev/cu.usbserial-10
ARDUINO_BAUD=9600

# Notification Settings (Optional)
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=your_twilio_number
```

### 5. Arduino Setup (Optional)

If you want to use Arduino for physical alerts:

1. **Install Required Libraries:**
   - Open Arduino IDE
   - Go to **Tools → Manage Libraries**
   - Install **LiquidCrystal_I2C** library
   - Install **Wire** library (usually pre-installed)

2. **Upload Arduino Code:**
   - Open `arduino_uno_drowsy_alert.ino` in Arduino IDE
   - Select your board: **Tools → Board → Arduino Uno**
   - Select your port: **Tools → Port → [Your Arduino Port]**
   - Click **Upload**

3. **Connect Components:**
   - Follow the circuit diagrams in `Images/Arduino Uno R3 Economy Circuits/`
   - Connect buzzer to pin 9
   - Connect Red LED to pin 10
   - Connect Green LED to pin 8
   - Connect I2C LCD to SDA/SCL pins

4. **Test Connection:**
   ```bash
   python test_arduino_connection.py
   ```

### 6. Run the Application

#### Option 1: Using Start Scripts (Recommended)

**Windows:**
1. Open Command Prompt or PowerShell
2. Navigate to project directory:
   ```bash
   cd "C:\path\to\AI-Drowsy-Driver-Detection"
   ```
3. Run Flask server:
   ```bash
   start_flask.bat
   ```

**macOS/Linux:**
1. Open Terminal
2. Navigate to project directory:
   ```bash
   cd "/path/to/AI-Drowsy-Driver-Detection"
   ```
3. Make script executable (first time only):
   ```bash
   chmod +x start_flask.sh
   ```
4. Run Flask server:
   ```bash
   ./start_flask.sh
   ```

#### Option 2: Manual Start

**Windows (Command Prompt):**
```bash
set FLASK_HOST=0.0.0.0
set FLASK_PORT=5000
python app.py
```

**Windows (PowerShell):**
```powershell
$env:FLASK_HOST="0.0.0.0"
$env:FLASK_PORT="5000"
python app.py
```

**macOS/Linux:**
```bash
export FLASK_HOST=0.0.0.0
export FLASK_PORT=5000
python3 app.py
```

### 7. Access the Application

- **Local Access:** Open your browser and go to `http://localhost:5000`
- **Network Access (Same WiFi):** Use your computer's IP address: `http://[YOUR_IP]:5000`
  - Find your IP:
    - **Windows:** Run `ipconfig` in Command Prompt, look for IPv4 Address
    - **macOS/Linux:** Run `ifconfig` or `ip addr`, look for inet address

### 8. Create Admin Account

1. Go to `http://localhost:5000/register.html`
2. Register with email and password
3. Select **Admin** role
4. Login at `http://localhost:5000/login.html`

### 9. Deploy for Public Access (Optional)

#### Option A: Using Cloudflare Tunnel (Recommended - Free)

Cloudflare Tunnel provides free, secure public access to your local Flask server without exposing your IP address.

**Step 1: Install Cloudflare Tunnel**

**Windows:**
1. Download `cloudflared.exe` from [Cloudflare Releases](https://github.com/cloudflare/cloudflared/releases/latest)
2. Place `cloudflared.exe` in your project folder (already included)
3. Or use the included `start_cloudflare.bat` script

**macOS:**
```bash
# Install via Homebrew (Recommended)
brew install cloudflared

# Or download manually from GitHub releases
# Place cloudflared in your project folder
```

**Step 2: Start Flask Server**

**Windows:**
```bash
# Open Command Prompt or PowerShell
cd "C:\path\to\AI-Drowsy-Driver-Detection"
start_flask.bat
```

**macOS/Linux:**
```bash
# Open Terminal
cd "/path/to/AI-Drowsy-Driver-Detection"
chmod +x start_flask.sh
./start_flask.sh
```

**Step 3: Start Cloudflare Tunnel (In a NEW Terminal/Command Prompt)**

**Windows:**
```bash
# Open a NEW Command Prompt window
cd "C:\path\to\AI-Drowsy-Driver-Detection"
start_cloudflare.bat

# Or manually:
cloudflared tunnel --url http://127.0.0.1:5000
```

**macOS/Linux:**
```bash
# Open a NEW Terminal window
cd "/path/to/AI-Drowsy-Driver-Detection"
chmod +x start_cloudflare.sh
./start_cloudflare.sh

# Or manually:
cloudflared tunnel --url http://127.0.0.1:5000
```

**Step 4: Get Your Public URL**

After starting Cloudflare Tunnel, you'll see output like:
```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable): |
|  https://random-words-1234.trycloudflare.com                                               |
+--------------------------------------------------------------------------------------------+
```

Copy this URL and share it to access your system from anywhere!

**Important Notes:**
- Keep BOTH terminals open (Flask server + Cloudflare tunnel)
- The URL changes each time you restart the tunnel
- Cloudflare tunnels are free but temporary (session-based)

#### Option B: Using ngrok (Alternative)

**Step 1: Install ngrok**

**Windows:**
1. Download `ngrok.exe` from [ngrok.com](https://ngrok.com/download)
2. Place `ngrok.exe` in your project folder (already included)
3. Sign up for a free account at ngrok.com to get your auth token
4. Run: `ngrok config add-authtoken YOUR_AUTH_TOKEN`

**macOS:**
```bash
# Install via Homebrew
brew install ngrok/ngrok/ngrok

# Or download from ngrok.com
# Sign up and get auth token, then:
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

**Step 2: Start Flask Server** (Same as Cloudflare Step 2)

**Step 3: Start ngrok Tunnel**

**Windows:**
```bash
start_ngrok.bat

# Or manually:
ngrok http 5000
```

**macOS/Linux:**
```bash
chmod +x start_ngrok.sh
./start_ngrok.sh

# Or manually:
ngrok http 5000
```

**Step 4: Get Your Public URL**

ngrok will display:
```
Forwarding  https://abc123.ngrok.io -> http://localhost:5000
```

Use the `https://` URL for public access.

#### Quick Start Commands Summary

**Windows - Full Setup:**
```bash
# Terminal 1 - Start Flask
start_flask.bat

# Terminal 2 - Start Cloudflare (after Flask is running)
start_cloudflare.bat
```

**macOS/Linux - Full Setup:**
```bash
# Terminal 1 - Start Flask
cd "/path/to/AI-Drowsy-Driver-Detection" && ./start_flask.sh

# Terminal 2 - Start Cloudflare (after Flask is running)
cd "/path/to/AI-Drowsy-Driver-Detection" && ./start_cloudflare.sh
```

#### Troubleshooting Hosting

**Flask won't start:**
- Check if port 5000 is already in use: `lsof -i :5000` (Mac) or `netstat -ano | findstr :5000` (Windows)
- Kill the process using the port if needed
- On Mac, disable AirPlay Receiver (uses port 5000)

**Cloudflare tunnel not connecting:**
- Ensure Flask is running first on port 5000
- Check firewall settings
- Verify `cloudflared` is installed correctly
- Try restarting both Flask and Cloudflare

**Can't access from other devices:**
- Ensure Flask is bound to `0.0.0.0` (not just `localhost`)
- Check that both Flask and tunnel are running
- Verify the tunnel URL is correct

---

## 📖 Usage Guide

### For Drivers

1. **Login:** Go to the login page and enter your credentials
2. **Start Monitoring:** Click "Start Monitoring" button
3. **Choose Camera:**
   - **Server Camera:** Uses connected USB webcam
   - **Browser Camera:** Uses your device's camera (click "Use Browser Cam")
4. **Monitor Metrics:** Watch real-time detection metrics displayed on your dashboard:
   - **EAR (Eye Aspect Ratio):** Measures how open your eyes are. Normal values are around 0.25-0.30. Lower values (below 0.23) indicate your eyes are closing, which triggers an alert.
   - **MAR (Mouth Aspect Ratio):** Measures how wide your mouth is open. Normal values are below 0.65. Higher values (above 0.65) indicate yawning, which is a sign of drowsiness.
   - **Head Tilt:** Measures the angle of your head in degrees. Normal values are less than 18°. Higher values indicate your head is tilting forward, backward, or to the side, which triggers an alert.
   - **PERCLOS (Percentage of Eye Closure):** Measures the percentage of time your eyes are closed over a period. Normal values are less than 20%. Higher values (above 20%) indicate your eyes are closed too often, triggering an alert.
   - *The progress bars show how close each metric is to triggering an alert. Each metric must stay in an alert state for a configured duration before an alert is triggered (this prevents false alarms).*
5. **Respond to Alerts:** If drowsiness is detected, acknowledge the alert to dismiss it

### For Administrators

1. **Monitor Drivers:** View all active drivers and their status in real-time
2. **Configure Settings:**
   - Adjust detection sensitivity for each metric (EAR, MAR, Head Tilt, PERCLOS)
   - Set metric timer thresholds (how long a metric must be in alert state before triggering)
   - Configure notification preferences (SMS, Email, Telegram, Arduino alerts)
   - *See "Understanding Detection Metrics" section below for detailed metric explanations*
3. **View History:** Review past drowsiness events and driver activity logs
4. **Manage Contacts:** Add emergency contacts for SMS notifications

*NOTE FOR ADMIN – Use the only one `DrowsyDet@gmail.com` account when applying settings so changes sync across all drivers.*

### Understanding Detection Metrics

The system uses four key metrics to detect drowsiness. Understanding these helps both drivers and administrators interpret alerts and configure the system effectively.

#### 1. EAR (Eye Aspect Ratio)
- **What it measures:** The ratio between the vertical and horizontal distances of your eyes. When you're alert, your eyes are open and the ratio is higher. When drowsy, your eyes close and the ratio decreases.
- **Normal range:** 0.25 - 0.30 (eyes open and alert)
- **Alert threshold:** Below 0.23 (eyes closing or closed)
- **What it detects:** Eye closure, prolonged blinking, or drooping eyelids
- **For drivers:** Keep your eyes open and facing forward. If the EAR value drops below 0.23 for several seconds, an alert will trigger.
- **For admins:** Lower EAR threshold = more sensitive (detects smaller eye closures). Higher threshold = less sensitive (requires more eye closure to trigger).

#### 2. MAR (Mouth Aspect Ratio)
- **What it measures:** The ratio of mouth opening width to height. When you yawn, your mouth opens wide, increasing this ratio.
- **Normal range:** Below 0.65 (mouth closed or slightly open)
- **Alert threshold:** Above 0.65 (yawning detected)
- **What it detects:** Yawning, which is a strong indicator of fatigue or drowsiness
- **For drivers:** Frequent yawning is a sign you should take a break. The system will alert when sustained yawning is detected.
- **For admins:** Higher MAR threshold = less sensitive (requires wider yawns). Lower threshold = more sensitive (detects smaller mouth openings).

#### 3. Head Tilt
- **What it measures:** The angle of your head relative to the vertical axis. When drowsy, drivers often tilt their head forward, backward, or to the side.
- **Normal range:** Less than 18 degrees (head upright and forward-facing)
- **Alert threshold:** More than 18 degrees (head tilted significantly)
- **What it detects:** Head nodding, head dropping forward, or tilting to the side
- **For drivers:** Keep your head upright and facing the road. If your head tilts more than 18 degrees for several seconds, an alert will trigger.
- **For admins:** Lower tilt threshold = more sensitive (detects smaller head movements). Higher threshold = less sensitive (requires more tilt to trigger).

#### 4. PERCLOS (Percentage of Eye Closure)
- **What it measures:** The percentage of time your eyes are closed over a rolling time window. This metric tracks prolonged eye closure over time, not just brief blinks.
- **Normal range:** Less than 20% (eyes open most of the time)
- **Alert threshold:** Above 20% (eyes closed for significant portion of time)
- **What it detects:** Microsleep episodes, prolonged eye closure, or frequent long blinks
- **For drivers:** This metric tracks if your eyes are closed too often. If PERCLOS exceeds 20%, it means your eyes are closed more than 20% of the time, indicating drowsiness.
- **For admins:** Higher PERCLOS threshold = less sensitive (allows more eye closure). Lower threshold = more sensitive (triggers with less eye closure).

#### How Metrics Work Together
- The system monitors all four metrics simultaneously
- An alert is triggered when any metric exceeds its threshold for the configured duration
- **False Alarm Prevention:** Each metric must remain in an alert state for a set duration (configurable by admins) before triggering, preventing brief moments from causing false alarms
- The progress bars in the driver dashboard show how close each metric is to triggering an alert

---

## 🔐 Security Features

- ✅ **Token-based Authentication** - Secure JWT tokens for session management
- ✅ **Password Hashing** - Bcrypt password encryption
- ✅ **Role-based Access Control** - Admin and Driver roles
- ✅ **CORS Protection** - Cross-origin resource sharing controls
- ✅ **Input Validation** - Sanitized user inputs

---

## 📁 Project Structure

```
AI-Drowsy-Driver-Detection/
├── app.py                          # Main Flask application
├── requirements.txt                # Python dependencies
├── arduino_uno_drowsy_alert.ino   # Arduino code
├── script.js                      # Frontend JavaScript
├── style.css                      # Custom styles
├── users.json                     # User database (JSON)
├── events.json                    # Event log
├── contacts.json                  # Emergency contacts
│
├── Images/                        # Project images
│   ├── Screenshots/               # Application screenshots
│   ├── Arduino Uno R3 Economy Circuits/  # Circuit diagrams
│   └── Arduino Library Manager/   # Library setup guides
│
├── Scope of Work/                 # Project documentation
│   └── AI Powered Drowsy Driver Detection System Scope of Work.docx
│
├── deployment/                     # Deployment scripts
│   ├── start_localtunnel.bat
│   └── TEST_NGROK.bat
│
├── HTML Pages/
│   ├── login.html                 # Login page
│   ├── register.html              # Registration page
│   ├── driver.html                # Driver dashboard
│   ├── admin.html                 # Admin dashboard
│   ├── settings.html              # Settings page
│   └── history.html               # Event history
│
└── Scripts/
    ├── start_flask.sh/.bat        # Flask startup scripts
    ├── start_cloudflare.sh/.bat  # Cloudflare tunnel scripts
    └── start_ngrok.sh/.bat       # ngrok tunnel scripts
```

---

## 🐛 Troubleshooting

### Camera Not Detected
- Ensure camera is connected and not used by another application
- Check camera permissions in system settings
- Try changing `CAMERA_INDEX` in settings (0, 1, 2, etc.)

### Arduino Not Connecting
- Verify Arduino is connected via USB
- Check port name in Settings (e.g., `/dev/cu.usbserial-10` on Mac, `COM3` on Windows)
- Ensure Arduino code is uploaded correctly
- Wait 2-3 seconds after enabling Arduino in settings

### Detection Not Working
- Ensure good lighting conditions
- Keep face centered in camera view
- Adjust detection sensitivity in Settings
- Check that MediaPipe is installed correctly

### Deployment Issues

**Flask Not Starting:**
- **Port 5000 Already in Use:**
  - **Windows:** Run `netstat -ano | findstr :5000` to find process, then `taskkill /PID [PID] /F`
  - **macOS/Linux:** Run `lsof -i :5000` to find process, then `kill -9 [PID]`
- **macOS Specific:** Disable AirPlay Receiver (System Settings → General → AirDrop & Handoff → AirPlay Receiver)

**Cloudflare Tunnel Issues:**
- Ensure Flask is running on port 5000 before starting tunnel
- **Windows:** Download `cloudflared.exe` from [GitHub Releases](https://github.com/cloudflare/cloudflared/releases)
- **macOS:** Install via `brew install cloudflared` or download manually
- Check firewall settings allow connections
- Verify both terminals are open (Flask + Cloudflare)

**ngrok Issues:**
- Sign up at [ngrok.com](https://ngrok.com) and get auth token
- Run `ngrok config add-authtoken YOUR_TOKEN` before using
- Free tier has session limits (8 hours)

### Performance Issues
- Lower camera resolution in Settings
- Reduce FPS setting
- Lower JPEG quality
- Close other applications using camera

---

## 📝 API Endpoints

### Authentication
- `POST /register` - Register new user
- `POST /login` - User login
- `POST /logout` - User logout

### Monitoring
- `POST /start` - Start monitoring session
- `POST /stop` - Stop monitoring session
- `GET /status` - Get current status
- `GET /video_feed/<driver_id>` - Video stream endpoint

### Settings
- `GET /settings` - Get current settings
- `POST /settings` - Update settings
- `GET /serial_ports` - List available Arduino ports
- `GET /arduino_status` - Get Arduino connection status

### Admin
- `GET /api/admin/drivers` - List all drivers
- `GET /api/admin/drivers/status` - Get all drivers' status
- `GET /events` - Get event history

### Frame Processing
- `POST /process_frame` - Process frame from browser camera

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 👥 Authors

- **Fernando Jose Reeves** - *Lead development & testing*
- **Mark Joseph Recosana** - *Secondary development & implementation*

---

## 🙏 Acknowledgments

- MediaPipe team for facial landmark detection
- OpenCV community for computer vision tools
- Flask framework developers
- Arduino community for hardware integration support

---

## 📚 References

- [MediaPipe Face Mesh Documentation](https://google.github.io/mediapipe/solutions/face_mesh)
- [OpenCV Documentation](https://docs.opencv.org/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Arduino Documentation](https://www.arduino.cc/reference/en/)

---

## 🔗 Related Projects

For a similar project structure reference, check out:
- [Django E-Commerce Project](https://github.com/mjrecosana06/DJANGO-ECommerce-Mark-Joseph-Recosana-BSIT-3B)

---

## 📞 Support

For issues, questions, or contributions, please open an issue on the GitHub repository.

---

**Note:** This system is designed for educational and research purposes. Always ensure proper testing before deploying in production environments.

