import os
import sys
import uuid
import collections
import time
import threading
import json
from datetime import datetime, date
from typing import Tuple, Optional
import re

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

import cv2
import numpy as np
import serial
import serial.tools.list_ports
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

try:
    import mediapipe as mp
except Exception as exc:  # pragma: no cover
    mp = None


def get_timestamp_iso() -> str:
    return datetime.utcnow().isoformat() + 'Z'


# Instance-based isolation: Each school/instance gets separate data files
# Set INSTANCE_ID environment variable or create instance_config.json
INSTANCE_ID = os.getenv('INSTANCE_ID', 'default')
try:
    if os.path.exists('instance_config.json'):
        with open('instance_config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            INSTANCE_ID = config.get('instance_id', INSTANCE_ID)
except Exception:
    pass

# Sanitize instance ID for filename safety
INSTANCE_ID = ''.join(c for c in INSTANCE_ID if c.isalnum() or c in ('-', '_')) or 'default'

# Instance-specific data files (defined early so classes can use them)
USERS_DB = f'users_{INSTANCE_ID}.json'
CONTACTS_DB = f'contacts_{INSTANCE_ID}.json'
EVENTS_DB = f'events_{INSTANCE_ID}.json'


class DrowsinessMonitor:
    def __init__(self):
        self.capture_index = int(os.getenv('CAMERA_INDEX', '0'))
        self.video_capture = None
        self.monitor_thread = None
        self.is_running = False
        self.frame_lock = threading.Lock()
        self.frame_available = threading.Condition(self.frame_lock)
        self.last_jpeg_frame: bytes | None = None
        self.current_status = {
            'state': 'IDLE',
            'ear': None,
            'confidence': None,
            'timestamp': get_timestamp_iso(),
            'running': False,
        }
        self.events_lock = threading.Lock()
        self.events: list[dict] = []
        self.ear_threshold = float(os.getenv('EAR_THRESHOLD', '0.23'))
        self.mar_threshold = float(os.getenv('MAR_THRESHOLD', '0.65'))
        self.tilt_threshold_deg = float(os.getenv('TILT_THRESHOLD_DEG', '18'))
        self.frames_below_threshold_required = int(os.getenv('FRAMES_BELOW_THRESH', '12'))
        self.perclos_threshold = float(os.getenv('PERCLOS_THRESHOLD', '0.2'))  # 20% default
        self._consec_below = 0
        self._consec_yawn = 0
        self._consec_tilt = 0
        # PERCLOS (percentage of time eyes are closed over recent window)
        self.perclos_window = collections.deque(maxlen=int(os.getenv('PERCLOS_WINDOW_FRAMES', '300')))
        self.perclos = None
        
        # Metric time tracking for timer thresholds (when metric entered alert state, duration)
        self.metric_times = {
            'ear': {'alert_start': None, 'duration_seconds': 0, 'last_update': None},
            'mar': {'alert_start': None, 'duration_seconds': 0, 'last_update': None},
            'headTilt': {'alert_start': None, 'duration_seconds': 0, 'last_update': None},
            'perclos': {'alert_start': None, 'duration_seconds': 0, 'last_update': None}
        }
        self.metric_times_lock = threading.Lock()

        # Camera/display encoding settings (optimized defaults for better performance)
        self.desired_width = int(os.getenv('CAM_WIDTH', '640'))
        self.desired_height = int(os.getenv('CAM_HEIGHT', '480'))
        # Lower FPS default for better performance (can be increased in settings if needed)
        self.desired_fps = int(os.getenv('CAM_FPS', '12'))
        self.mirror_display = str(os.getenv('CAM_MIRROR', '0')).lower() in ('1', 'true', 'yes')
        try:
            # Lower default quality for better performance (60 is good balance)
            self.jpeg_quality = max(30, min(95, int(os.getenv('JPEG_QUALITY', '60'))))
        except Exception:
            self.jpeg_quality = 60

        # IoT/Arduino
        self.iot_enabled = False
        self.serial_port_name = os.getenv('ARDUINO_PORT', '')
        self.serial_baud = int(os.getenv('ARDUINO_BAUD', '9600'))
        self.serial_conn: serial.Serial | None = None
        self.snooze_until_ts = 0.0
        # Last known client location for emergency SMS linkage
        self.last_location: dict | None = None

        # MediaPipe FaceMesh setup (lazy until start)
        self.face_mesh = None
        self.drawing_spec = None

    def _ensure_facemesh(self):
        if mp is None:
            raise RuntimeError('mediapipe is not installed')
        if self.face_mesh is None:
            self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )

    @staticmethod
    def _eye_aspect_ratio_from_landmarks(landmarks: np.ndarray) -> float:
        # Using MediaPipe FaceMesh indices for eye landmarks (refined)
        # Left eye (example indices)
        left_idxs = [33, 160, 158, 133, 153, 144]
        right_idxs = [263, 387, 385, 362, 380, 373]

        def ear_for_indices(idxs: list[int]) -> float:
            p1, p2, p3, p4, p5, p6 = [landmarks[i] for i in idxs]
            # EAR = (|p2 - p6| + |p3 - p5|) / (2 * |p1 - p4|)
            def dist(a, b):
                return np.linalg.norm(a - b)
            return (dist(p2, p6) + dist(p3, p5)) / (2.0 * dist(p1, p4) + 1e-6)

        left_ear = ear_for_indices(left_idxs)
        right_ear = ear_for_indices(right_idxs)
        return float((left_ear + right_ear) / 2.0)

    @staticmethod
    def _mouth_aspect_ratio(landmarks: np.ndarray) -> float:
        # Use upper/lower lip center and mouth width
        # Indices: 13 (upper lip), 14 (lower lip), 78 (left mouth), 308 (right mouth)
        p_up = landmarks[13]
        p_low = landmarks[14]
        p_left = landmarks[78]
        p_right = landmarks[308]
        def dist(a, b):
            return np.linalg.norm(a - b)
        vertical = dist(p_up, p_low)
        horizontal = dist(p_left, p_right) + 1e-6
        return float(vertical / horizontal)

    @staticmethod
    def _eye_line_tilt_deg(landmarks: np.ndarray) -> float:
        # Angle of the line between outer eye corners relative to horizontal
        # Indices: 33 (left eye outer), 263 (right eye outer)
        p_left = landmarks[33]
        p_right = landmarks[263]
        dy = p_right[1] - p_left[1]
        dx = p_right[0] - p_left[0] + 1e-6
        angle_rad = np.arctan2(dy, dx)
        return float(abs(np.degrees(angle_rad)))

    def _append_event(self, event: dict):
        with self.events_lock:
            self.events.append(event)
            # Persist to disk best-effort
            try:
                with open(EVENTS_DB, 'w', encoding='utf-8') as f:
                    json.dump(self.events, f, indent=2)
            except Exception:
                pass
    
    def _update_metric_time(self, metric_key: str, is_in_alert_state: bool, current_value: float | None = None):
        """
        Update metric time tracking for timer thresholds.
        Tracks when metric entered alert state and duration.
        
        Args:
            metric_key: 'ear', 'mar', 'headTilt', or 'perclos'
            is_in_alert_state: True if metric is currently in alert state
            current_value: Current metric value (for reference)
        """
        with self.metric_times_lock:
            now = time.time()
            metric_time = self.metric_times.get(metric_key)
            if not metric_time:
                return
            
            if is_in_alert_state:
                # Metric is in alert state
                if metric_time['alert_start'] is None:
                    # Just entered alert state
                    metric_time['alert_start'] = now
                    metric_time['last_update'] = get_timestamp_iso()
                # Update duration
                metric_time['duration_seconds'] = now - metric_time['alert_start']
            else:
                # Metric is not in alert state - reset tracking
                if metric_time['alert_start'] is not None:
                    # Just exited alert state
                    metric_time['last_update'] = get_timestamp_iso()
                metric_time['alert_start'] = None
                metric_time['duration_seconds'] = 0
                if current_value is not None:
                    metric_time['last_update'] = get_timestamp_iso()
    
    def _get_metric_time_data(self, metric_key: str) -> dict:
        """Get formatted metric time data for API responses."""
        with self.metric_times_lock:
            metric_time = self.metric_times.get(metric_key, {})
            alert_start = metric_time.get('alert_start')
            duration_seconds = metric_time.get('duration_seconds', 0)
            last_update = metric_time.get('last_update', 'Never')
            
            # Format duration
            if duration_seconds < 60:
                duration_str = f"{int(duration_seconds)}s"
            elif duration_seconds < 3600:
                minutes = int(duration_seconds // 60)
                seconds = int(duration_seconds % 60)
                duration_str = f"{minutes}m {seconds}s"
            else:
                hours = int(duration_seconds // 3600)
                minutes = int((duration_seconds % 3600) // 60)
                duration_str = f"{hours}h {minutes}m"
            
            return {
                'value': '--' if alert_start is None else f"{duration_str}",
                'duration': duration_str if alert_start is not None else '--',
                'last_update': last_update,
                'raw': duration_seconds,
                'duration_seconds': duration_seconds,
                'alert_start': alert_start
            }

    def start(self):
        if self.is_running:
            return
        self._ensure_facemesh()
        indices_to_try = [self.capture_index] + [i for i in range(0, 4) if i != self.capture_index]
        self.video_capture = self._open_camera_for_indices(indices_to_try)
        if not self.video_capture or not self.video_capture.isOpened():
            raise RuntimeError('Unable to open any camera (tried indices %s)' % indices_to_try)
        self._apply_capture_properties()
        self.is_running = True
        self.current_status.update({'running': True, 'state': 'ALERT', 'timestamp': get_timestamp_iso()})
        self._consec_below = 0

        # Load events from disk (best-effort) on first start
        if not self.events:
            try:
                if os.path.exists(EVENTS_DB):
                    with open(EVENTS_DB, 'r', encoding='utf-8') as f:
                        self.events = json.load(f)
            except Exception:
                self.events = []

        self.monitor_thread = threading.Thread(target=self._run_loop, name='DrowsinessMonitorThread', daemon=True)
        self.monitor_thread.start()

    def _open_camera_for_indices(self, indices: list[int]) -> cv2.VideoCapture | None:
        preferred_backends = []
        if sys.platform == 'darwin':
            preferred_backends = [cv2.CAP_AVFOUNDATION]
        elif sys.platform.startswith('win'):
            preferred_backends = [cv2.CAP_DSHOW]
        else:
            preferred_backends = [cv2.CAP_V4L2, cv2.CAP_ANY]
        for idx in indices:
            # Try preferred backends
            for be in preferred_backends:
                cap = cv2.VideoCapture(idx, be)
                if cap and cap.isOpened():
                    self.capture_index = idx
                    return cap
                try:
                    if cap:
                        cap.release()
                except Exception:
                    pass
            # Fallback without specifying backend
            cap = cv2.VideoCapture(idx)
            if cap and cap.isOpened():
                self.capture_index = idx
                return cap
            try:
                if cap:
                    cap.release()
            except Exception:
                pass
        return None

    def _apply_capture_properties(self):
        try:
            if self.video_capture:
                if self.desired_width > 0:
                    self.video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.desired_width))
                if self.desired_height > 0:
                    self.video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.desired_height))
                if self.desired_fps > 0:
                    self.video_capture.set(cv2.CAP_PROP_FPS, float(self.desired_fps))
        except Exception:
            pass

    def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        if self.video_capture is not None:
            try:
                self.video_capture.release()
            except Exception:
                pass
        with self.frame_lock:
            self.frame_available.notify_all()
        self.current_status.update({'running': False, 'state': 'IDLE', 'timestamp': get_timestamp_iso()})
        # Stop alarm on Arduino
        self._send_iot_command('SAFE')

    def _run_loop(self):
        previous_state = 'ALERT'
        while self.is_running and self.video_capture and self.video_capture.isOpened():
            ok, frame = self.video_capture.read()
            if not ok:
                time.sleep(0.02)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb)

            ear_value = None
            mar_value = None
            tilt_deg = None
            state = 'ALERT'
            confidence = None
            reason = None

            if results.multi_face_landmarks:
                h, w = frame.shape[:2]
                face_landmarks = results.multi_face_landmarks[0]
                pts = np.array([[lm.x * w, lm.y * h] for lm in face_landmarks.landmark], dtype=np.float32)
                try:
                    ear_value = self._eye_aspect_ratio_from_landmarks(pts)
                    mar_value = self._mouth_aspect_ratio(pts)
                    tilt_deg = self._eye_line_tilt_deg(pts)

                    # Eyes - Update metric time tracking
                    ear_in_alert = ear_value < self.ear_threshold
                    if ear_in_alert:
                        self._consec_below += 1
                        self.perclos_window.append(1)
                    else:
                        self._consec_below = 0
                        self.perclos_window.append(0)
                    self._update_metric_time('ear', ear_in_alert, ear_value)

                    # Yawn - Update metric time tracking
                    mar_in_alert = mar_value > self.mar_threshold
                    if mar_in_alert:
                        self._consec_yawn += 1
                    else:
                        self._consec_yawn = 0
                    self._update_metric_time('mar', mar_in_alert, mar_value)

                    # Tilt - Update metric time tracking
                    tilt_in_alert = tilt_deg > self.tilt_threshold_deg
                    if tilt_in_alert:
                        self._consec_tilt += 1
                    else:
                        self._consec_tilt = 0
                    self._update_metric_time('headTilt', tilt_in_alert, tilt_deg)

                    
                    # Check metric timer thresholds (from METRIC_TIMERS)
                    with METRIC_TIMERS_LOCK:
                        ear_timer = METRIC_TIMERS.get('ear_threshold_duration', 2)
                        mar_timer = METRIC_TIMERS.get('mar_threshold_duration', 1)
                        tilt_timer = METRIC_TIMERS.get('tilt_threshold_duration', 1)
                        perclos_timer = METRIC_TIMERS.get('perclos_threshold_duration', 2)
                    
                    # Get metric time data
                    ear_time_data = self._get_metric_time_data('ear')
                    mar_time_data = self._get_metric_time_data('mar')
                    tilt_time_data = self._get_metric_time_data('headTilt')
                    perclos_time_data = self._get_metric_time_data('perclos')
                    
                    # Check if metric has been in alert state long enough
                    ear_timer_triggered = ear_in_alert and ear_time_data['duration_seconds'] >= ear_timer
                    mar_timer_triggered = mar_in_alert and mar_time_data['duration_seconds'] >= mar_timer
                    tilt_timer_triggered = tilt_in_alert and tilt_time_data['duration_seconds'] >= tilt_timer
                    
                    # STRICT detection: Require BOTH timer AND consecutive frames to reduce false positives
                    # EAR: Must have enough consecutive frames AND timer must be triggered
                    drowsy_eyes = (self._consec_below >= self.frames_below_threshold_required) and ear_timer_triggered
                    
                    # Yawning: Require timer AND high consecutive frames (very strict to avoid false positives)
                    drowsy_yawn = (self._consec_yawn >= max(8, self.frames_below_threshold_required // 2)) and mar_timer_triggered
                    
                    # Head tilt: Require timer AND high consecutive frames
                    drowsy_tilt = (self._consec_tilt >= max(10, self.frames_below_threshold_required // 2)) and tilt_timer_triggered
                    
                    # PERCLOS: Check after calculation (done later in the code)
                    drowsy_perclos = False  # Will be set after PERCLOS calculation

                    # Final check: only trigger if conditions are met
                    # drowsy_perclos will be set later after PERCLOS calculation
                    if drowsy_eyes or drowsy_yawn or drowsy_tilt:
                        state = 'DROWSY'
                        if drowsy_eyes:
                            reason = 'eyes closed (EAR)'
                            confidence = min(1.0, max(0.0, (self.ear_threshold - (ear_value or self.ear_threshold)) / max(0.15, self.ear_threshold)))
                        elif drowsy_yawn:
                            reason = 'yawning (MAR)'
                            # Confidence as normalized margin above threshold
                            confidence = min(1.0, max(0.0, ((mar_value or self.mar_threshold) - self.mar_threshold) / max(0.4, self.mar_threshold)))
                        elif drowsy_tilt:
                            reason = 'head tilt'
                            confidence = min(1.0, max(0.0, ((tilt_deg or self.tilt_threshold_deg) - self.tilt_threshold_deg) / max(20.0, self.tilt_threshold_deg)))
                        elif drowsy_perclos:
                            reason = 'high PERCLOS (prolonged eye closure)'
                            # Normalize PERCLOS confidence: map from threshold to threshold+0.3 (50%)
                            confidence = min(1.0, max(0.0, ((self.perclos or self.perclos_threshold) - self.perclos_threshold) / 0.3))
                    else:
                        state = 'ALERT'
                        confidence = 1.0
                        reason = None
                except Exception:
                    state = 'ALERT'
                    confidence = None
                    reason = None

            # Update PERCLOS from window (must be done before metric time tracking)
            if len(self.perclos_window) > 0:
                try:
                    self.perclos = float(sum(self.perclos_window)) / float(len(self.perclos_window))
                except Exception:
                    self.perclos = None
            else:
                self.perclos = None
            
            # PERCLOS metric time tracking (already updated above in the if block)
            # Just ensure it's tracked here too for consistency
            perclos_in_alert = self.perclos is not None and self.perclos > self.perclos_threshold
            self._update_metric_time('perclos', perclos_in_alert, self.perclos)

            # Overlay status on frame
            overlay = frame.copy()
            label = f"{state}"
            color = (0, 200, 0) if state == 'ALERT' else (0, 0, 255)
            cv2.rectangle(overlay, (10, 10), (290, 90), (255, 255, 255), -1)
            cv2.putText(overlay, label, (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3, cv2.LINE_AA)
            if ear_value is not None:
                cv2.putText(overlay, f"EAR: {ear_value:.3f}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 60, 60), 2, cv2.LINE_AA)
            if mar_value is not None:
                cv2.putText(overlay, f"MAR: {mar_value:.3f}", (150, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 60, 60), 2, cv2.LINE_AA)
            if tilt_deg is not None:
                cv2.putText(overlay, f"Tilt: {tilt_deg:.1f}deg", (280, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 60, 60), 2, cv2.LINE_AA)

            # Mirror display if requested (affects display only)
            if self.mirror_display:
                try:
                    overlay = cv2.flip(overlay, 1)
                except Exception:
                    pass

            # Optimize JPEG encoding: use optimized quality and progressive encoding for faster streaming
            encode_params = [
                int(cv2.IMWRITE_JPEG_QUALITY), int(self.jpeg_quality),
                int(cv2.IMWRITE_JPEG_OPTIMIZE), 1,  # Enable optimization
            ]
            ok, jpeg = cv2.imencode('.jpg', overlay, encode_params)
            if ok:
                # Only update frame if it's been consumed (optimization: skip frames if client is slow)
                with self.frame_lock:
                    # Always update the latest frame (client will get the most recent one)
                    self.last_jpeg_frame = jpeg.tobytes()
                    self.frame_available.notify_all()

            # Snooze feature removed

            # Update status and log events on transition to DROWSY
            now_iso = get_timestamp_iso()
            self.current_status = {
                'state': state,
                'ear': ear_value,
                'mar': mar_value,
                'tiltDeg': tilt_deg,
                'perclos': self.perclos,
                'confidence': confidence,
                'timestamp': now_iso,
                'running': True,
                'reason': reason,
                'metric_times': {
                    'ear': self._get_metric_time_data('ear'),
                    'mar': self._get_metric_time_data('mar'),
                    'headTilt': self._get_metric_time_data('headTilt'),
                    'perclos': self._get_metric_time_data('perclos')
                }
            }
            # Send Arduino command on state change OR periodically to ensure sync
            if state != previous_state:
                previous_state = state
                # Send command immediately on state change
                self._send_iot_command('ALERT' if state == 'DROWSY' else 'SAFE')
            else:
                # Periodically send state every 30 frames (~2 seconds at 15 FPS) to ensure Arduino stays in sync
                if not hasattr(self, '_arduino_sync_counter'):
                    self._arduino_sync_counter = 0
                self._arduino_sync_counter += 1
                if self._arduino_sync_counter >= 30:
                    self._arduino_sync_counter = 0
                    # Send current state to ensure Arduino is in sync
                    self._send_iot_command('ALERT' if state == 'DROWSY' else 'SAFE')
                event = {
                    'time': now_iso,
                    'type': 'Drowsiness' if state == 'DROWSY' else 'Alert',
                    'confidence': confidence,
                    'notes': f"Detected {reason}" if state == 'DROWSY' else 'Driver alert',
                }
                # Attach last known location (if any) for history verification and SMS
                try:
                    loc = getattr(monitor, 'last_location', None)
                    if isinstance(loc, dict):
                        lat = loc.get('lat'); lon = loc.get('lon')
                        if lat is not None and lon is not None:
                            event['location'] = {
                                'lat': float(lat),
                                'lon': float(lon),
                                'time': loc.get('time'),
                                'accuracy': loc.get('accuracy'),
                            }
                except Exception:
                    pass
                self._append_event(event)
                # On DROWSY, attempt all notifications (SMS, Email, Telegram) (best-effort)
                if state == 'DROWSY':
                    try:
                        # Get driver email from monitor to filter contacts
                        driver_email = getattr(self, '_user_email', None)
                        trigger_all_notifications(event, driver_email=driver_email)
                    except Exception:
                        pass

            # Target FPS based on desired_fps setting (default 15 FPS = 0.066s)
            # But allow faster processing if needed for responsiveness
            target_delay = 1.0 / max(10, min(30, self.desired_fps))
            time.sleep(target_delay)

    def frame_generator(self):
        """Generate MJPEG stream with frame rate limiting for better performance"""
        boundary = b'--frame\r\n'
        headers = b'Content-Type: image/jpeg\r\n\r\n'
        last_frame_time = 0
        target_fps = max(10, min(30, self.desired_fps))  # Limit to 10-30 FPS
        frame_interval = 1.0 / target_fps
        
        while True:
            current_time = time.time()
            # Rate limit: only send frame if enough time has passed
            if current_time - last_frame_time < frame_interval:
                time.sleep(0.01)  # Small sleep to prevent busy waiting
                continue
            
            with self.frame_lock:
                if self.last_jpeg_frame is None:
                    self.frame_available.wait(timeout=1.0)
                frame = self.last_jpeg_frame
            
            if frame is None:
                # If not running, stop stream
                if not self.is_running:
                    break
                continue
            
            last_frame_time = current_time
            yield boundary + headers + frame + b'\r\n'

    # -------- Arduino / IoT helpers --------
    # Each monitor instance has its own Arduino connection (per-user)
    def _send_iot_command(self, cmd: str):
        """Send command to user's own Arduino - fails gracefully if Arduino not connected"""
        # Get user email from monitor if available
        user_email = getattr(self, '_user_email', '')
        try:
            # Use per-user Arduino connection
            if user_email:
                user_arduino = get_or_create_user_arduino(user_email)
                user_arduino.send_command(cmd, user_email)
            else:
                # Fallback to shared Arduino for legacy support
                shared_arduino.send_command(cmd, user_email)
        except Exception:
            # Arduino command failed - continue detection anyway (Arduino is optional)
            pass


app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ==================== SHARED ARDUINO CONNECTION ====================
# Global Arduino connection that all users share
class SharedArduinoManager:
    """Manages a single shared Arduino connection for all users"""
    def __init__(self):
        self.serial_conn: serial.Serial | None = None
        self.serial_port_name = os.getenv('ARDUINO_PORT', '')
        self.serial_baud = int(os.getenv('ARDUINO_BAUD', '9600'))
        self.iot_enabled = False
        self.lock = threading.Lock()
        self.last_command_time = 0
        self.heartbeat_thread = None
        self.heartbeat_running = False
    
    def set_port(self, port_name: str):
        """Set the serial port name and open connection if enabled"""
        with self.lock:
            old_port = self.serial_port_name
            self.serial_port_name = port_name
            # Close existing connection if port changed
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.close()
                except Exception:
                    pass
                self.serial_conn = None
            
            # If enabled and port is set, try to open connection immediately (even if same port, to ensure it's open)
            if self.iot_enabled and self.serial_port_name:
                try:
                    self._open_serial()
                    if self.serial_conn and self.serial_conn.is_open:
                        print(f"Arduino port set to {port_name} and connection opened")
                    else:
                        print(f"Warning: Failed to open Arduino connection on {port_name}")
                except Exception as e:
                    print(f"Error opening Arduino on {port_name}: {e}")
    
    def set_enabled(self, enabled: bool):
        """Enable or disable Arduino connection"""
        with self.lock:
            self.iot_enabled = enabled
            if not enabled:
                self._stop_heartbeat()
                if self.serial_conn:
                    try:
                        self.serial_conn.close()
                    except Exception:
                        pass
                self.serial_conn = None
                print("Arduino disabled")
            else:
                # If enabling and port is set, try to open connection immediately
                if self.serial_port_name:
                    try:
                        self._open_serial()
                        if self.serial_conn and self.serial_conn.is_open:
                            print(f"Arduino enabled and connected on {self.serial_port_name}")
                        else:
                            print(f"Warning: Arduino enabled but failed to open connection on {self.serial_port_name}")
                    except Exception as e:
                        print(f"Error enabling Arduino: {e}")
                else:
                    print("Warning: Arduino enabled but no port selected")
                self._start_heartbeat()
    
    def _open_serial(self):
        """Open serial connection if not already open - fails gracefully if Arduino not connected"""
        if not self.iot_enabled or not self.serial_port_name:
            return
        
        # Test if connection is already open and alive
        if self.serial_conn and self.serial_conn.is_open:
            try:
                # Test if port is still accessible by checking if we can read status
                self.serial_conn.in_waiting  # Check if port is still accessible
                # Connection is good, don't reopen
                return
            except Exception:
                # Connection is dead, close it
                try:
                    self.serial_conn.close()
                except Exception:
                    pass
                self.serial_conn = None
        
        # Try to open serial connection
        try:
            print(f"Attempting to open Arduino on {self.serial_port_name}...")
            self.serial_conn = serial.Serial(
                self.serial_port_name, 
                self.serial_baud, 
                timeout=1, 
                write_timeout=3,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            # Wait for Arduino to initialize (Arduino resets on serial connection)
            time.sleep(2.0)  # Increased wait time for Arduino to fully initialize
            # Clear any pending data
            self.serial_conn.reset_input_buffer()
            self.serial_conn.reset_output_buffer()
            # Test connection by flushing
            self.serial_conn.flush()
            # Send initial heartbeat to confirm connection works
            try:
                self.serial_conn.write(b'CAM:ACTIVE\n')
                self.serial_conn.flush()
                print(f"Arduino connection opened successfully on {self.serial_port_name}")
            except Exception as e:
                print(f"Warning: Arduino opened but initial heartbeat failed: {e}")
        except (serial.SerialException, OSError, ValueError) as e:
            # Arduino not connected or port unavailable - fail gracefully
            print(f"Error: Failed to open Arduino on {self.serial_port_name}: {e}")
            self.serial_conn = None
        except Exception as e:
            # Any other error - also fail gracefully
            print(f"Unexpected error opening Arduino: {e}")
            self.serial_conn = None
    
    def send_command(self, cmd: str, user_email: str = ''):
        """Send command to Arduino (shared by all users) - completely non-blocking, fails gracefully"""
        # Don't block if not enabled
        if not self.iot_enabled:
            return
        
        # For critical commands (ALERT/SAFE), try harder to acquire lock
        lock_acquired = False
        if cmd in ('ALERT', 'SAFE'):
            # For critical commands, try to acquire lock (with short timeout)
            lock_acquired = self.lock.acquire(blocking=True, timeout=0.5)  # Increased timeout for reliability
        else:
            lock_acquired = self.lock.acquire(blocking=False)
        
        if not lock_acquired:
            return  # Skip if lock is held (non-critical operation)
        
        try:
            # Ensure connection is open before sending
            if not self.serial_conn or not self.serial_conn.is_open:
                self._open_serial()
            
            # If still not connected, return silently
            if not self.serial_conn or not self.serial_conn.is_open:
                return
            
            try:
                # Include user info in command if provided (for Arduino display)
                if user_email:
                    # Format: USER:email@example.com|ALERT or USER:email@example.com|SAFE
                    command_str = f"USER:{user_email}|{cmd.strip()}\n"
                else:
                    command_str = cmd.strip() + '\n'
                payload = command_str.encode('utf-8')
                
                # Don't clear input buffer - might lose important data
                # Just flush output to ensure clean send
                self.serial_conn.flush()
                
                # Write command
                bytes_written = self.serial_conn.write(payload)
                
                # Flush after writing to ensure data is sent immediately
                self.serial_conn.flush()
                self.last_command_time = time.time()
                
                # Verify bytes were written (basic sanity check)
                if bytes_written != len(payload):
                    # Retry once if write was incomplete
                    try:
                        time.sleep(0.01)  # Small delay before retry
                        self.serial_conn.write(payload)
                        self.serial_conn.flush()
                    except Exception:
                        pass
            except (serial.SerialException, OSError, ValueError):
                # Connection lost - close and reset silently
                try:
                    if self.serial_conn:
                        self.serial_conn.close()
                except Exception:
                    pass
                finally:
                    self.serial_conn = None
            except Exception:
                # Any other error - also fail gracefully
                try:
                    if self.serial_conn:
                        self.serial_conn.close()
                except Exception:
                    pass
                self.serial_conn = None
        finally:
            if lock_acquired:
                self.lock.release()
    
    def _start_heartbeat(self):
        """Start heartbeat thread to keep Arduino connection alive and sync state - fails gracefully if Arduino not connected"""
        if self.heartbeat_running:
            return
        self.heartbeat_running = True
        def heartbeat_loop():
            consecutive_failures = 0
            max_failures = 10  # Increased tolerance for failures (allow more retries)
            
            while self.heartbeat_running:
                time.sleep(2)  # Send heartbeat every 2 seconds (more frequent to prevent timeout)
                
                # Quick check without blocking
                if not self.iot_enabled:
                    break
                
                try:
                    # Try to acquire lock without blocking
                    if self.lock.acquire(blocking=False):
                        try:
                            # Only open if not already open (avoid frequent reopens)
                            if not self.serial_conn or not self.serial_conn.is_open:
                                self._open_serial()
                            
                            if self.serial_conn and self.serial_conn.is_open:
                                # Send CAM:ACTIVE as heartbeat to keep connection alive
                                try:
                                    self.serial_conn.flush()
                                    self.serial_conn.write(b'CAM:ACTIVE\n')
                                    self.serial_conn.flush()
                                    consecutive_failures = 0  # Reset on success
                                except Exception:
                                    # Write failed, connection might be dead
                                    consecutive_failures += 1
                                    try:
                                        if self.serial_conn:
                                            self.serial_conn.close()
                                    except Exception:
                                        pass
                                    self.serial_conn = None
                            else:
                                consecutive_failures += 1
                        except Exception:
                            consecutive_failures += 1
                            # Try to reconnect on failure
                            try:
                                if self.serial_conn:
                                    self.serial_conn.close()
                            except Exception:
                                pass
                            self.serial_conn = None
                        finally:
                            self.lock.release()
                    else:
                        # Couldn't acquire lock, but don't count as failure (might be busy sending command)
                        pass
                    
                    # Stop heartbeat if Arduino consistently unavailable
                    if consecutive_failures >= max_failures:
                        self.heartbeat_running = False
                        break
                except Exception:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        self.heartbeat_running = False
                        break
        self.heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
    
    def _stop_heartbeat(self):
        """Stop heartbeat thread"""
        self.heartbeat_running = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=1)
            self.heartbeat_thread = None

# Global shared Arduino instance (for admin/legacy support)
shared_arduino = SharedArduinoManager()

# Per-user Arduino connections: each user (driver) can have their own Arduino
USER_ARDUINOS = {}  # {email: SharedArduinoManager instance}
USER_ARDUINOS_LOCK = threading.Lock()

def get_or_create_user_arduino(email: str) -> SharedArduinoManager:
    """Get or create a per-user Arduino connection"""
    with USER_ARDUINOS_LOCK:
        if email not in USER_ARDUINOS:
            user_arduino = SharedArduinoManager()
            USER_ARDUINOS[email] = user_arduino
        return USER_ARDUINOS[email]

# Multi-driver monitoring: each driver gets their own monitor instance
DRIVER_MONITORS = {}  # {email: DrowsinessMonitor instance}
DRIVER_MONITORS_LOCK = threading.Lock()

# Global detection settings (shared across all monitors)
GLOBAL_SETTINGS = {
    'ear_threshold': float(os.getenv('EAR_THRESHOLD', '0.23')),
    'mar_threshold': float(os.getenv('MAR_THRESHOLD', '0.65')),
    'tilt_threshold_deg': float(os.getenv('TILT_THRESHOLD_DEG', '18')),
    'frames_below_threshold_required': int(os.getenv('FRAMES_BELOW_THRESH', '12')),
    'perclos_threshold': float(os.getenv('PERCLOS_THRESHOLD', '0.2')),  # 20% default
}
GLOBAL_SETTINGS_LOCK = threading.Lock()

def apply_global_settings_to_monitor(mon: 'DrowsinessMonitor'):
    """Apply global settings to a monitor instance."""
    with GLOBAL_SETTINGS_LOCK:
        mon.ear_threshold = GLOBAL_SETTINGS['ear_threshold']
        mon.mar_threshold = GLOBAL_SETTINGS['mar_threshold']
        mon.tilt_threshold_deg = GLOBAL_SETTINGS['tilt_threshold_deg']
        mon.frames_below_threshold_required = GLOBAL_SETTINGS['frames_below_threshold_required']
        mon.perclos_threshold = GLOBAL_SETTINGS['perclos_threshold']

        # Create admin monitor and apply global settings
monitor = DrowsinessMonitor()  # Legacy single monitor (for admin or first user)
monitor._user_email = 'admin'  # Set admin email for Arduino commands
apply_global_settings_to_monitor(monitor)

def get_or_create_driver_monitor(email: str) -> DrowsinessMonitor:
    """Get or create a DrowsinessMonitor instance for a specific driver."""
    with DRIVER_MONITORS_LOCK:
        if email not in DRIVER_MONITORS:
            new_monitor = DrowsinessMonitor()
            apply_global_settings_to_monitor(new_monitor)
            # Store user email in monitor for Arduino commands
            new_monitor._user_email = email
            DRIVER_MONITORS[email] = new_monitor
        return DRIVER_MONITORS[email]

def get_driver_monitor(email: str) -> DrowsinessMonitor | None:
    """Get a driver's monitor if it exists."""
    with DRIVER_MONITORS_LOCK:
        return DRIVER_MONITORS.get(email)

def cleanup_inactive_monitors():
    """Cleanup monitors for drivers who have been offline for too long."""
    with DRIVER_MONITORS_LOCK:
        to_remove = []
        for email, mon in DRIVER_MONITORS.items():
            if not mon.is_running:
                to_remove.append(email)
        for email in to_remove:
            try:
                DRIVER_MONITORS[email].stop()
                del DRIVER_MONITORS[email]
            except Exception:
                pass

# Periodic cleanup of inactive monitors (every 5 minutes)
def _periodic_cleanup():
    while True:
        time.sleep(300)  # 5 minutes
        try:
            cleanup_inactive_monitors()
        except Exception:
            pass

_cleanup_thread = threading.Thread(target=_periodic_cleanup, daemon=True)
_cleanup_thread.start()

# ---- Simple token auth (demo) ----
app.secret_key = os.getenv('FLASK_SECRET', 'dev-secret-change-me')
serializer = URLSafeTimedSerializer(app.secret_key)
# Note: Instance config and data file paths are defined earlier in the file

# Admin emails override (comma-separated), ensures listed users are admins
ADMIN_EMAILS = set()
try:
    raw = os.getenv('ADMIN_EMAILS', '')
    if raw:
        ADMIN_EMAILS = {e.strip().lower() for e in raw.split(',') if e.strip()}
except Exception:
    ADMIN_EMAILS = set()

def _is_admin_email(email: str) -> bool:
    try:
        return (email or '').strip().lower() in ADMIN_EMAILS
    except Exception:
        return False


def _get_user_role(email: str) -> str:
    """
    Resolve the role for a given email from users.json or ADMIN_EMAILS override.
    """
    try:
        if _is_admin_email(email):
            return 'admin'
        users = _load_users()
        u = users.get((email or '').strip().lower())
        if u:
            return (u.get('role') or '').strip().lower()
    except Exception:
        pass
    return ''


def _load_users() -> dict:
    try:
        if os.path.exists(USERS_DB):
            with open(USERS_DB, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_users(users: dict):
    try:
        with open(USERS_DB, 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=2)
    except Exception:
        pass




def _load_contacts() -> list:
    try:
        if os.path.exists(CONTACTS_DB):
            with open(CONTACTS_DB, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_contacts(contacts: list):
    try:
        with open(CONTACTS_DB, 'w', encoding='utf-8') as f:
            json.dump(contacts, f, indent=2)
    except Exception:
        pass


def create_token(email: str) -> str:
    return serializer.dumps({'email': email})


def verify_token(token: str) -> str | None:
    try:
        data = serializer.loads(token, max_age=60 * 60 * 24 * 7)
        return data.get('email')
    except (BadSignature, SignatureExpired):
        return None


# ---- SMS using Twilio (optional) ----
def _twilio_client():  # pragma: no cover
    try:
        from twilio.rest import Client
    except Exception:
        return None
    sid = os.getenv('TWILIO_ACCOUNT_SID')
    token = os.getenv('TWILIO_AUTH_TOKEN')
    if not sid or not token:
        return None
    try:
        return Client(sid, token)
    except Exception:
        return None


def trigger_sms_notifications(event: dict, driver_email: str = None) -> int:  # pragma: no cover
    client = _twilio_client()
    from_number = os.getenv('TWILIO_FROM_NUMBER')
    if not client or not from_number:
        return 0
    all_contacts = _load_contacts()
    # Filter contacts by driver email (owner field)
    if driver_email:
        contacts = [c for c in all_contacts if c.get('owner') == driver_email and c.get('active', True)]
    else:
        contacts = [c for c in all_contacts if c.get('active', True)]
    # Include Google Maps link if we have a recent client-provided location
    message = f"Drowsiness alert at {event.get('time', '')}: {event.get('notes', '')}"
    try:
        loc = getattr(monitor, 'last_location', None)
        if isinstance(loc, dict):
            lat = loc.get('lat')
            lon = loc.get('lon')
            if lat is not None and lon is not None:
                maps = f" https://maps.google.com/?q={lat},{lon}"
                message += f" Location:{maps}"
    except Exception:
        pass
    sent = 0
    for c in contacts:
        try:
            if not c.get('notify', False) or not c.get('phone'):
                continue
            client.messages.create(to=c['phone'], from_=from_number, body=message)
            sent += 1
        except Exception:
            continue
    return sent


# ---- Email Notifications (FREE) ----
def send_email_notification(to_email: str, subject: str, message: str) -> bool:
    """Send email notification using SMTP (Gmail or other)"""
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # Get email configuration from environment variables
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_email = os.getenv('SMTP_EMAIL')
        smtp_password = os.getenv('SMTP_PASSWORD')
        
        if not smtp_email or not smtp_password:
            return False
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = smtp_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add message body
        msg.attach(MIMEText(message, 'plain'))
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
        
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def trigger_email_notifications(event: dict, driver_email: str = None) -> int:
    """Trigger email notifications to all active contacts with email, filtered by driver email"""
    all_contacts = _load_contacts()
    # Filter contacts by driver email (owner field)
    if driver_email:
        contacts = [c for c in all_contacts if c.get('owner') == driver_email and c.get('active', True)]
    else:
        contacts = [c for c in all_contacts if c.get('active', True)]
    
    # Build message
    subject = f"🚨 Drowsiness Alert - {event.get('type', 'Alert')}"
    message = f"""
AI Driver Safety Alert

⚠️ Drowsiness Detected!

Time: {event.get('time', 'N/A')}
Type: {event.get('type', 'Alert')}
Details: {event.get('notes', 'Driver showing signs of drowsiness')}
Confidence: {int(event.get('confidence', 0) * 100) if event.get('confidence') else 'N/A'}%

"""
    
    # Add location if available
    try:
        loc = getattr(monitor, 'last_location', None)
        if isinstance(loc, dict):
            lat = loc.get('lat')
            lon = loc.get('lon')
            if lat is not None and lon is not None:
                maps_link = f"https://maps.google.com/?q={lat},{lon}"
                message += f"\n📍 Location: {maps_link}\n"
    except Exception:
        pass
    
    message += "\n⚠️ Please check on the driver immediately!\n\n---\nAI Driver Safety System"
    
    sent = 0
    for c in contacts:
        try:
            # Check if contact is active and has email
            if not c.get('active', True):
                continue
            email = c.get('email', '').strip()
            if not email:
                continue
            
            if send_email_notification(email, subject, message):
                sent += 1
        except Exception as e:
            print(f"Failed to send email to {c.get('name', 'unknown')}: {e}")
            continue
    
    return sent


# ---- Telegram Bot Notifications (FREE) ----
def send_telegram_notification(chat_id: str, message: str) -> bool:
    """Send notification via Telegram bot"""
    try:
        import requests
        
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token or not chat_id:
            return False
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


def trigger_telegram_notifications(event: dict, driver_email: str = None) -> int:
    """Trigger Telegram notifications to all active contacts with Telegram, filtered by driver email"""
    all_contacts = _load_contacts()
    # Filter contacts by driver email (owner field)
    if driver_email:
        contacts = [c for c in all_contacts if c.get('owner') == driver_email and c.get('active', True)]
    else:
        contacts = [c for c in all_contacts if c.get('active', True)]
    
    # Build message with HTML formatting
    message = f"""
🚨 <b>AI Driver Safety Alert</b> 🚨

⚠️ <b>Drowsiness Detected!</b>

<b>Time:</b> {event.get('time', 'N/A')}
<b>Type:</b> {event.get('type', 'Alert')}
<b>Details:</b> {event.get('notes', 'Driver showing signs of drowsiness')}
<b>Confidence:</b> {int(event.get('confidence', 0) * 100) if event.get('confidence') else 'N/A'}%
"""
    
    # Add location if available
    try:
        loc = getattr(monitor, 'last_location', None)
        if isinstance(loc, dict):
            lat = loc.get('lat')
            lon = loc.get('lon')
            if lat is not None and lon is not None:
                maps_link = f"https://maps.google.com/?q={lat},{lon}"
                message += f"\n📍 <b>Location:</b> <a href='{maps_link}'>View on Map</a>\n"
    except Exception:
        pass
    
    message += "\n⚠️ <b>Please check on the driver immediately!</b>"
    
    sent = 0
    for c in contacts:
        try:
            # Check if contact is active and has Telegram
            if not c.get('active', True):
                continue
            telegram_id = c.get('telegram', '').strip()
            if not telegram_id:
                continue
            
            if send_telegram_notification(telegram_id, message):
                sent += 1
        except Exception as e:
            print(f"Failed to send Telegram to {c.get('name', 'unknown')}: {e}")
            continue
    
    return sent


# ---- Unified Notification Trigger ----
def trigger_all_notifications(event: dict, driver_email: str = None) -> dict:
    """
    Trigger all enabled notification methods (SMS, Email, Telegram)
    Filters contacts by driver_email (owner field) to ensure only driver's contacts are notified
    Returns a dict with counts for each method
    """
    results = {
        'sms': 0,
        'email': 0,
        'telegram': 0,
        'total': 0
    }
    
    try:
        # Try SMS (Twilio - paid)
        sms_sent = trigger_sms_notifications(event, driver_email=driver_email)
        results['sms'] = sms_sent
        results['total'] += sms_sent
    except Exception as e:
        print(f"SMS notification failed: {e}")
    
    try:
        # Try Email (FREE)
        email_sent = trigger_email_notifications(event, driver_email=driver_email)
        results['email'] = email_sent
        results['total'] += email_sent
    except Exception as e:
        print(f"Email notification failed: {e}")
    
    try:
        # Try Telegram (FREE)
        telegram_sent = trigger_telegram_notifications(event, driver_email=driver_email)
        results['telegram'] = telegram_sent
        results['total'] += telegram_sent
    except Exception as e:
        print(f"Telegram notification failed: {e}")
    
    return results


@app.route('/test_sms', methods=['POST'])
def test_sms():  # pragma: no cover
    """Test SMS notifications (Twilio - Paid)"""
    try:
        contacts = _load_contacts()
        eligible = [c for c in contacts if c.get('active', True) and c.get('phone')]
        event = {
            'time': get_timestamp_iso(),
            'type': 'TestSMS',
            'confidence': None,
            'notes': 'Manual test SMS from admin',
        }
        sent = trigger_sms_notifications(event)
        twilio_ready = bool(_twilio_client()) and bool(os.getenv('TWILIO_FROM_NUMBER'))
        return jsonify({'ok': True, 'sent': int(sent), 'eligible': len(eligible), 'twilioReady': twilio_ready}), 200
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.route('/test_email', methods=['POST'])
def test_email():
    """Test Email notifications (FREE)"""
    try:
        contacts = _load_contacts()
        eligible = [c for c in contacts if c.get('active', True) and c.get('email')]
        event = {
            'time': get_timestamp_iso(),
            'type': 'Test Alert',
            'confidence': 0.85,
            'notes': 'Manual test email from admin - System is working correctly!',
        }
        sent = trigger_email_notifications(event)
        email_ready = bool(os.getenv('SMTP_EMAIL')) and bool(os.getenv('SMTP_PASSWORD'))
        return jsonify({
            'ok': True, 
            'sent': int(sent), 
            'eligible': len(eligible), 
            'emailReady': email_ready,
            'message': f'Sent to {sent} of {len(eligible)} contacts' if sent > 0 else 'No emails sent. Check configuration.'
        }), 200
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.route('/test_telegram', methods=['POST'])
def test_telegram():
    """Test Telegram notifications (FREE)"""
    try:
        contacts = _load_contacts()
        eligible = [c for c in contacts if c.get('active', True) and c.get('telegram')]
        event = {
            'time': get_timestamp_iso(),
            'type': 'Test Alert',
            'confidence': 0.85,
            'notes': 'Manual test notification from admin - System is working correctly!',
        }
        sent = trigger_telegram_notifications(event)
        telegram_ready = bool(os.getenv('TELEGRAM_BOT_TOKEN'))
        return jsonify({
            'ok': True, 
            'sent': int(sent), 
            'eligible': len(eligible), 
            'telegramReady': telegram_ready,
            'message': f'Sent to {sent} of {len(eligible)} contacts' if sent > 0 else 'No messages sent. Check configuration.'
        }), 200
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.route('/test_all_notifications', methods=['POST'])
def test_all_notifications():
    """Test all notification methods at once"""
    try:
        event = {
            'time': get_timestamp_iso(),
            'type': 'Test Alert',
            'confidence': 0.85,
            'notes': 'Manual test from admin - All notification systems check!',
        }
        results = trigger_all_notifications(event)
        
        contacts = _load_contacts()
        eligible_counts = {
            'sms': len([c for c in contacts if c.get('active', True) and c.get('phone')]),
            'email': len([c for c in contacts if c.get('active', True) and c.get('email')]),
            'telegram': len([c for c in contacts if c.get('active', True) and c.get('telegram')])
        }
        
        return jsonify({
            'ok': True,
            'results': results,
            'eligible': eligible_counts,
            'message': f"Sent {results['total']} notifications (SMS: {results['sms']}, Email: {results['email']}, Telegram: {results['telegram']})"
        }), 200
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.route('/start', methods=['POST'])
def start_monitoring():
    """Legacy endpoint - starts the default monitor or driver-specific monitor"""
    try:
        data = request.get_json(silent=True) or {}
        driver_email = (data.get('driver_email') or '').strip().lower()
        
        if driver_email:
            # Start monitoring for specific driver
            driver_monitor = get_or_create_driver_monitor(driver_email)
            driver_monitor.start()
            return jsonify({'ok': True, 'running': True, 'driver': driver_email}), 200
        else:
            # Start default monitor (legacy behavior)
            monitor.start()
            return jsonify({'ok': True, 'running': True}), 200
    except Exception as exc:  # pragma: no cover
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.route('/stop', methods=['POST'])
def stop_monitoring():
    """Legacy endpoint - stops the default monitor or driver-specific monitor"""
    data = request.get_json(silent=True) or {}
    driver_email = (data.get('driver_email') or '').strip().lower()
    
    if driver_email:
        driver_monitor = get_driver_monitor(driver_email)
        if driver_monitor:
            driver_monitor.stop()
        return jsonify({'ok': True, 'running': False, 'driver': driver_email}), 200
    else:
        monitor.stop()
        return jsonify({'ok': True, 'running': False}), 200


@app.route('/status', methods=['GET'])
def get_status():
    """Get status - can be for default monitor or specific driver"""
    driver_email = (request.args.get('driver') or '').strip().lower()
    
    if driver_email:
        driver_monitor = get_driver_monitor(driver_email)
        if driver_monitor:
            status = driver_monitor.current_status.copy()
            # Ensure metric_times are included (from current_status or calculate fresh)
            if 'metric_times' not in status or not status['metric_times']:
                status['metric_times'] = {
                    'ear': driver_monitor._get_metric_time_data('ear'),
                    'mar': driver_monitor._get_metric_time_data('mar'),
                    'headTilt': driver_monitor._get_metric_time_data('headTilt'),
                    'perclos': driver_monitor._get_metric_time_data('perclos')
                }
            # Add metric timer thresholds and value thresholds
            with METRIC_TIMERS_LOCK:
                status['metric_timers'] = {
                    'ear': METRIC_TIMERS['ear_threshold_duration'],
                    'mar': METRIC_TIMERS['mar_threshold_duration'],
                    'tilt': METRIC_TIMERS['tilt_threshold_duration'],
                    'perclos': METRIC_TIMERS['perclos_threshold_duration']
                }
            with GLOBAL_SETTINGS_LOCK:
                status['value_thresholds'] = {
                    'ear': GLOBAL_SETTINGS['ear_threshold'],
                    'mar': GLOBAL_SETTINGS['mar_threshold'],
                    'tilt': GLOBAL_SETTINGS['tilt_threshold_deg'],
                    'perclos': GLOBAL_SETTINGS['perclos_threshold']
                }
            return jsonify(status), 200
        # Return idle status instead of 404 for better UX
        return jsonify({
            'state': 'IDLE', 
            'running': False, 
            'ear': None,
            'mar': None,
            'tiltDeg': None,
            'perclos': None,
            'confidence': None,
            'timestamp': get_timestamp_iso(),
            'reason': 'Driver monitor not initialized'
        }), 200
    
    status = monitor.current_status.copy()
    # Add metric timer thresholds and value thresholds for default monitor too
    with METRIC_TIMERS_LOCK:
        status['metric_timers'] = {
            'ear': METRIC_TIMERS['ear_threshold_duration'],
            'mar': METRIC_TIMERS['mar_threshold_duration'],
            'tilt': METRIC_TIMERS['tilt_threshold_duration'],
            'perclos': METRIC_TIMERS['perclos_threshold_duration']
        }
    with GLOBAL_SETTINGS_LOCK:
        status['value_thresholds'] = {
            'ear': GLOBAL_SETTINGS['ear_threshold'],
            'mar': GLOBAL_SETTINGS['mar_threshold'],
            'tilt': GLOBAL_SETTINGS['tilt_threshold_deg'],
            'perclos': GLOBAL_SETTINGS['perclos_threshold']
        }
    return jsonify(status), 200


@app.route('/video_feed')
def video_feed():
    """Legacy video feed endpoint"""
    if not monitor.is_running:
        # Return empty stream if not started
        def empty_gen():
            yield b''
        response = Response(empty_gen(), mimetype='multipart/x-mixed-replace; boundary=frame')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    
    response = Response(monitor.frame_generator(), mimetype='multipart/x-mixed-replace; boundary=frame')
    # Add headers to prevent caching and ensure smooth streaming
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-Accel-Buffering'] = 'no'  # Disable buffering for nginx if used
    return response


@app.route('/video_feed/<path:driver_id>')
def video_feed_driver(driver_id: str):
    """Driver-specific video feed endpoint"""
    # Driver ID is URL-encoded email
    from urllib.parse import unquote
    driver_email = unquote(driver_id).strip().lower()
    
    driver_monitor = get_driver_monitor(driver_email)
    if not driver_monitor or not driver_monitor.is_running:
        # Return empty stream
        def empty_gen():
            yield b''
        response = Response(empty_gen(), mimetype='multipart/x-mixed-replace; boundary=frame')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    
    response = Response(driver_monitor.frame_generator(), mimetype='multipart/x-mixed-replace; boundary=frame')
    # Add headers to prevent caching and ensure smooth streaming
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-Accel-Buffering'] = 'no'  # Disable buffering for nginx if used
    return response


@app.route('/events', methods=['GET'])
def get_events():
    with monitor.events_lock:
        return jsonify(monitor.events[-200:]), 200


# -------- Helpers for user context --------
def _get_user_email_from_request(default=None):
    """
    Extract user email from Bearer token or fallback headers.
    """
    user_email = default
    try:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            payload = serializer.loads(token, max_age=86400 * 7)
            user_email = (payload.get('email') or user_email or '').strip().lower()
    except Exception:
        pass

    # Fallback: explicit header
    if not user_email:
        user_email = (request.headers.get('X-User-Email') or '').strip().lower()
    return user_email


@app.route('/clear_events', methods=['POST'])
def clear_events():
    with monitor.events_lock:
        monitor.events = []
        try:
            if os.path.exists(EVENTS_DB):
                os.remove(EVENTS_DB)
        except Exception:
            pass
    return jsonify({'ok': True}), 200


# -------- Contacts CRUD --------
@app.route('/contacts', methods=['GET'])
def get_contacts():
    user_email = _get_user_email_from_request()
    contacts = _load_contacts()
    role_hdr = (request.headers.get('X-User-Role') or '').strip().lower()
    role_resolved = role_hdr or _get_user_role(user_email)
    is_admin = role_resolved == 'admin'

    # If no user email and not admin, return empty to avoid leaking data
    if not user_email and not is_admin:
        return jsonify([]), 200

    # Admin can see all contacts
    if is_admin:
        return jsonify(contacts), 200

    # Filter contacts by owner for non-admins
    filtered = [c for c in contacts if (c.get('owner') or '').lower() == user_email]
    return jsonify(filtered), 200


@app.route('/contacts', methods=['POST'])
def add_contact():
    user_email = _get_user_email_from_request()
    role_hdr = (request.headers.get('X-User-Role') or '').strip().lower()
    role_resolved = role_hdr or _get_user_role(user_email)
    is_admin = role_resolved == 'admin'
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    email = (data.get('email') or '').strip()
    telegram = (data.get('telegram') or '').strip()
    relationship = (data.get('relationship') or '').strip()
    priority = (data.get('priority') or 'normal').strip()
    active = bool(data.get('active', True))
    if not user_email and not is_admin:
        return jsonify({'ok': False, 'error': 'User email required'}), 400
    
    # At least one contact method required
    if not name:
        return jsonify({'ok': False, 'error': 'Name is required'}), 400
    if not phone and not email and not telegram:
        return jsonify({'ok': False, 'error': 'At least one contact method (phone, email, or telegram) is required'}), 400
    
    contacts = _load_contacts()
    new_c = {
        'id': str(uuid.uuid4()), 
        'name': name, 
        'phone': phone,
        'email': email,
        'telegram': telegram,
        'relationship': relationship,
        'priority': priority,
        'active': active,
        'owner': user_email or ''
    }
    contacts.append(new_c)
    _save_contacts(contacts)
    return jsonify({'ok': True, 'contact': new_c}), 201


@app.route('/contacts/<cid>', methods=['PUT'])
def update_contact(cid: str):
    user_email = _get_user_email_from_request()
    role_hdr = (request.headers.get('X-User-Role') or '').strip().lower()
    role_resolved = role_hdr or _get_user_role(user_email)
    is_admin = role_resolved == 'admin'
    data = request.get_json(silent=True) or {}
    contacts = _load_contacts()
    
    # Support both UUID and index-based updates (for backward compatibility)
    updated = None
    try:
        # Try as index first (for old admin.html compatibility)
        index = int(cid)
        if 0 <= index < len(contacts):
            c = contacts[index]
            if not is_admin and user_email and (c.get('owner') or '').lower() != user_email:
                return jsonify({'ok': False, 'error': 'Forbidden'}), 403
            if 'name' in data: c['name'] = (data['name'] or '').strip()
            if 'phone' in data: c['phone'] = (data['phone'] or '').strip()
            if 'email' in data: c['email'] = (data['email'] or '').strip()
            if 'telegram' in data: c['telegram'] = (data['telegram'] or '').strip()
            if 'relationship' in data: c['relationship'] = (data['relationship'] or '').strip()
            if 'priority' in data: c['priority'] = (data['priority'] or 'normal').strip()
            if 'active' in data: c['active'] = bool(data['active'])
            # Legacy 'notify' field support
            if 'notify' in data: c['active'] = bool(data['notify'])
            updated = c
    except (ValueError, TypeError):
        # Try as UUID
        for c in contacts:
            if c.get('id') == cid:
                if not is_admin and user_email and (c.get('owner') or '').lower() != user_email:
                    return jsonify({'ok': False, 'error': 'Forbidden'}), 403
                if 'name' in data: c['name'] = (data['name'] or '').strip()
                if 'phone' in data: c['phone'] = (data['phone'] or '').strip()
                if 'email' in data: c['email'] = (data['email'] or '').strip()
                if 'telegram' in data: c['telegram'] = (data['telegram'] or '').strip()
                if 'relationship' in data: c['relationship'] = (data['relationship'] or '').strip()
                if 'priority' in data: c['priority'] = (data['priority'] or 'normal').strip()
                if 'active' in data: c['active'] = bool(data['active'])
                # Legacy 'notify' field support
                if 'notify' in data: c['active'] = bool(data['notify'])
                updated = c
                break
    
    if not updated:
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    _save_contacts(contacts)
    return jsonify({'ok': True, 'contact': updated}), 200


@app.route('/contacts/<cid>', methods=['DELETE'])
def delete_contact(cid: str):
    user_email = _get_user_email_from_request()
    role_hdr = (request.headers.get('X-User-Role') or '').strip().lower()
    role_resolved = role_hdr or _get_user_role(user_email)
    is_admin = role_resolved == 'admin'
    contacts = _load_contacts()
    
    # Support both UUID and index-based deletion (for backward compatibility)
    new_list = contacts
    try:
        # Try as index first (for old admin.html compatibility)
        index = int(cid)
        if 0 <= index < len(contacts):
            if (not is_admin) and user_email and (contacts[index].get('owner') or '').lower() != user_email:
                return jsonify({'ok': False, 'error': 'Forbidden'}), 403
            new_list = contacts[:index] + contacts[index+1:]
    except (ValueError, TypeError):
        # Try as UUID
        new_list = []
        found = False
        for c in contacts:
            if c.get('id') == cid:
                if (not is_admin) and user_email and (c.get('owner') or '').lower() != user_email:
                    return jsonify({'ok': False, 'error': 'Forbidden'}), 403
                found = True
                continue
            new_list.append(c)
    
    if len(new_list) == len(contacts):
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    _save_contacts(new_list)
    return jsonify({'ok': True}), 200


@app.route('/settings', methods=['GET'])
def get_settings():
    """Get current settings including per-user Arduino settings"""
    # Get current user from token
    user_email = None
    try:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            try:
                payload = serializer.loads(token, max_age=86400)
                user_email = payload.get('email', '').strip().lower()
            except Exception:
                pass
    except Exception:
        pass
    
    # Use per-user Arduino if user is logged in, otherwise use shared Arduino
    target_arduino = shared_arduino
    if user_email:
        target_arduino = get_or_create_user_arduino(user_email)
    
    response_data = {
        'ok': True, 
        'earThreshold': GLOBAL_SETTINGS['ear_threshold'],
        'marThreshold': GLOBAL_SETTINGS['mar_threshold'],
        'tiltThreshold': GLOBAL_SETTINGS['tilt_threshold_deg'],
        'framesBelow': GLOBAL_SETTINGS['frames_below_threshold_required'],
        'perclosThreshold': GLOBAL_SETTINGS['perclos_threshold'],
        'iotEnabled': target_arduino.iot_enabled, 
        'serialPort': target_arduino.serial_port_name
    }
    
    # Add metric timer settings
    with METRIC_TIMERS_LOCK:
        response_data['metricTimers'] = {
            'ear': METRIC_TIMERS['ear_threshold_duration'],
            'mar': METRIC_TIMERS['mar_threshold_duration'],
            'tilt': METRIC_TIMERS['tilt_threshold_duration'],
            'perclos': METRIC_TIMERS['perclos_threshold_duration']
        }
    
    return jsonify(response_data), 200


@app.route('/settings', methods=['POST'])
def update_settings():
    data = request.get_json(silent=True) or {}
    
    # Metric timer thresholds (duration before alert)
    timer_changed = False
    with METRIC_TIMERS_LOCK:
        if 'earThresholdDuration' in data:
            val = int(data['earThresholdDuration'])
            if 1 <= val <= 60:
                METRIC_TIMERS['ear_threshold_duration'] = val
                timer_changed = True
        if 'marThresholdDuration' in data:
            val = int(data['marThresholdDuration'])
            if 1 <= val <= 60:
                METRIC_TIMERS['mar_threshold_duration'] = val
                timer_changed = True
        if 'tiltThresholdDuration' in data:
            val = int(data['tiltThresholdDuration'])
            if 1 <= val <= 60:
                METRIC_TIMERS['tilt_threshold_duration'] = val
                timer_changed = True
        if 'perclosThresholdDuration' in data:
            val = int(data['perclosThresholdDuration'])
            if 1 <= val <= 60:
                METRIC_TIMERS['perclos_threshold_duration'] = val
                timer_changed = True
    
    # Detection thresholds (applied globally to all monitors)
    settings_changed = False
    
    # EAR threshold
    ear_threshold = data.get('earThreshold')
    if isinstance(ear_threshold, (int, float)) and 0.15 <= ear_threshold <= 0.35:
        with GLOBAL_SETTINGS_LOCK:
            GLOBAL_SETTINGS['ear_threshold'] = float(ear_threshold)
        settings_changed = True
    
    # MAR threshold
    mar_threshold = data.get('marThreshold')
    if isinstance(mar_threshold, (int, float)) and 0.4 <= mar_threshold <= 0.8:
        with GLOBAL_SETTINGS_LOCK:
            GLOBAL_SETTINGS['mar_threshold'] = float(mar_threshold)
        settings_changed = True
    
    # Tilt threshold
    tilt_threshold = data.get('tiltThreshold')
    if isinstance(tilt_threshold, (int, float)) and 10 <= tilt_threshold <= 30:
        with GLOBAL_SETTINGS_LOCK:
            GLOBAL_SETTINGS['tilt_threshold_deg'] = float(tilt_threshold)
        settings_changed = True
    
    # Frames below threshold
    frames_below = data.get('framesBelow')
    if isinstance(frames_below, int) and 3 <= frames_below <= 30:
        with GLOBAL_SETTINGS_LOCK:
            GLOBAL_SETTINGS['frames_below_threshold_required'] = frames_below
        settings_changed = True
    
    # PERCLOS threshold
    perclos_threshold = data.get('perclosThreshold')
    if isinstance(perclos_threshold, (int, float)) and 0.05 <= perclos_threshold <= 0.5:
        with GLOBAL_SETTINGS_LOCK:
            GLOBAL_SETTINGS['perclos_threshold'] = float(perclos_threshold)
        settings_changed = True
    
    # Apply to admin monitor
    if settings_changed:
        apply_global_settings_to_monitor(monitor)
        
        # Apply to all existing driver monitors
        with DRIVER_MONITORS_LOCK:
            for driver_monitor in DRIVER_MONITORS.values():
                apply_global_settings_to_monitor(driver_monitor)
    
    # Legacy sensitivity parameter (for backward compatibility)
    sensitivity = data.get('sensitivity')  # 0..100 from UI
    if isinstance(sensitivity, (int, float)):
        # Map 0..100 to EAR threshold range [0.18 .. 0.30] (lower = more sensitive)
        t_min, t_max = 0.18, 0.30
        normalized = max(0.0, min(1.0, float(sensitivity) / 100.0))
        # Inverse map so higher UI setting means higher sensitivity (lower threshold)
        ear_val = t_max - normalized * (t_max - t_min)
        with GLOBAL_SETTINGS_LOCK:
            GLOBAL_SETTINGS['ear_threshold'] = ear_val
        apply_global_settings_to_monitor(monitor)
        with DRIVER_MONITORS_LOCK:
            for driver_monitor in DRIVER_MONITORS.values():
                apply_global_settings_to_monitor(driver_monitor)
    
    # IoT settings - PER-USER Arduino support (each driver can have their own Arduino)
    # Get current user from token or request data
    user_email = None
    try:
        # Try from request data first (more reliable)
        user_email = data.get('user_email', '').strip().lower()
        
        # Fallback to Authorization header
        if not user_email:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
                try:
                    payload = serializer.loads(token, max_age=86400)
                    user_email = payload.get('email', '').strip().lower()
                except Exception:
                    pass
    except Exception:
        pass
    
    # Use per-user Arduino if user is logged in, otherwise use shared Arduino
    target_arduino = shared_arduino
    if user_email:
        target_arduino = get_or_create_user_arduino(user_email)
    
    # IMPORTANT: Set port FIRST, then enable, so connection can be opened properly
    serial_port = data.get('serialPort')
    if isinstance(serial_port, str) and serial_port:
        try:
            target_arduino.set_port(serial_port)
            # Also update legacy monitor for backward compatibility
            monitor.serial_port_name = serial_port
        except Exception as e:
            # Log error but don't fail - Arduino is optional
            print(f"Warning: Failed to set Arduino port: {e}")
    
    iot_enabled = data.get('iotEnabled')
    if isinstance(iot_enabled, bool):
        try:
            target_arduino.set_enabled(iot_enabled)
            # Also update legacy monitor for backward compatibility
            monitor.iot_enabled = iot_enabled
            
            # Verify connection was opened if enabled
            if iot_enabled and serial_port:
                # Give it a moment to open
                time.sleep(0.5)
                with target_arduino.lock:
                    if target_arduino.serial_conn and target_arduino.serial_conn.is_open:
                        print(f"Arduino connected successfully on {serial_port}")
                    else:
                        print(f"Warning: Arduino port {serial_port} enabled but connection not open")
        except Exception as e:
            # Log error but don't fail - Arduino is optional
            print(f"Warning: Failed to enable Arduino: {e}")
    
    response_data = {
        'ok': True, 
        'earThreshold': GLOBAL_SETTINGS['ear_threshold'],
        'marThreshold': GLOBAL_SETTINGS['mar_threshold'],
        'tiltThreshold': GLOBAL_SETTINGS['tilt_threshold_deg'],
        'framesBelow': GLOBAL_SETTINGS['frames_below_threshold_required'],
        'perclosThreshold': GLOBAL_SETTINGS['perclos_threshold'],
        'iotEnabled': target_arduino.iot_enabled, 
        'serialPort': target_arduino.serial_port_name
    }
    
    # Add metric timer settings
    with METRIC_TIMERS_LOCK:
        response_data['metricTimers'] = {
            'ear': METRIC_TIMERS['ear_threshold_duration'],
            'mar': METRIC_TIMERS['mar_threshold_duration'],
            'tilt': METRIC_TIMERS['tilt_threshold_duration'],
            'perclos': METRIC_TIMERS['perclos_threshold_duration']
        }
    
    return jsonify(response_data), 200


@app.route('/serial_ports', methods=['GET'])
def serial_ports():
    """Get list of available serial ports - fails gracefully if no ports available"""
    ports = []
    try:
        for p in serial.tools.list_ports.comports():
            ports.append({'device': p.device, 'description': p.description})
    except Exception:
        pass
    return jsonify(ports), 200


@app.route('/arduino_status', methods=['GET'])
def arduino_status():
    """Get Arduino connection status for debugging"""
    user_email = None
    try:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            try:
                payload = serializer.loads(token, max_age=86400)
                user_email = payload.get('email', '').strip().lower()
            except Exception:
                pass
    except Exception:
        pass
    
    target_arduino = shared_arduino
    if user_email:
        target_arduino = get_or_create_user_arduino(user_email)
    
    with target_arduino.lock:
        status = {
            'enabled': target_arduino.iot_enabled,
            'port': target_arduino.serial_port_name,
            'connected': target_arduino.serial_conn is not None and target_arduino.serial_conn.is_open if target_arduino.serial_conn else False,
            'heartbeat_running': target_arduino.heartbeat_running
        }
    
    return jsonify(status), 200


# -------- Multi-Driver Monitoring API --------
# Storage for driver sessions (in-memory for demo, use Redis/DB in production)
DRIVER_SESSIONS = {}
DRIVER_SESSIONS_LOCK = threading.Lock()

# Metric timer thresholds (configurable by admin)
METRIC_TIMERS = {
    # Optimized defaults for faster, more responsive detection
    'ear_threshold_duration': int(os.getenv('EAR_THRESHOLD_DURATION_SEC', '2')),  # Reduced from 5 to 2 seconds
    'mar_threshold_duration': int(os.getenv('MAR_THRESHOLD_DURATION_SEC', '1')),  # Reduced from 3 to 1 second
    'tilt_threshold_duration': int(os.getenv('TILT_THRESHOLD_DURATION_SEC', '1')),  # Reduced from 3 to 1 second
    'perclos_threshold_duration': int(os.getenv('PERCLOS_THRESHOLD_DURATION_SEC', '2')),  # Reduced from 5 to 2 seconds
}
METRIC_TIMERS_LOCK = threading.Lock()

@app.route('/api/admin/users', methods=['GET'])
def get_all_users():
    """Admin endpoint to get all users"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'ok': False, 'error': 'Authentication required'}), 401
    
    try:
        admin_email = serializer.loads(token, max_age=86400 * 7)
    except (BadSignature, SignatureExpired):
        return jsonify({'ok': False, 'error': 'Invalid or expired token'}), 401
    
    users = _load_users()
    admin_user = users.get(admin_email)
    if not admin_user or admin_user.get('role', '').lower() != 'admin':
        return jsonify({'ok': False, 'error': 'Admin access required'}), 403
    
    # Return users with sensitive data filtered (no password hashes)
    safe_users = {}
    for email, user_data in users.items():
        safe_users[email] = {
            'email': email,
            'role': user_data.get('role', 'driver'),
            'name': user_data.get('name', '')
        }
    
    return jsonify({'ok': True, 'users': safe_users}), 200


@app.route('/api/admin/drivers/status', methods=['GET'])
def get_all_drivers_status():
    """
    Admin-only endpoint to get status of all registered drivers.
    Returns driver information including online status, metrics, and alert counts.
    """
    try:
        # Load all users
        users = _load_users()
        
        # Filter only driver accounts (non-admin)
        drivers = []
        with DRIVER_SESSIONS_LOCK:
            for email, user_data in users.items():
                # Skip admin accounts
                if user_data.get('role', 'user').lower() == 'admin':
                    continue
                
                # Get driver name from email or use email as name
                name = email.split('@')[0].replace('.', ' ').title()
                
                # Check if driver has an active session
                session_data = DRIVER_SESSIONS.get(email, {})
                is_online = session_data.get('is_online', False)
                is_monitoring = session_data.get('is_monitoring', False)
                last_active = session_data.get('last_active', 'Never')
                state = session_data.get('state', 'IDLE')
                
                # Get metrics from session or use defaults
                metrics = session_data.get('metrics', {
                    'ear': '--',
                    'mar': '--',
                    'perclos': '--',
                    'headTilt': '--'
                })
                
                # Get metric timestamps and durations
                metric_times = session_data.get('metric_times', {})
                
                # Format metrics for display with time information
                formatted_metrics = {}
                for key, val in metrics.items():
                    metric_time_info = metric_times.get(key, {})
                    duration_sec = metric_time_info.get('duration_seconds', 0)
                    last_update = metric_time_info.get('last_update', 'Never')
                    
                    if val != '--':
                        if key == 'ear' or key == 'mar':
                            formatted_value = f"{float(val):.3f}" if isinstance(val, (int, float)) else val
                        elif key == 'perclos':
                            if isinstance(val, (int, float)):
                                formatted_value = f"{int(float(val) * 100)}%" if val < 1 else f"{int(val)}%"
                            else:
                                formatted_value = val
                        elif key == 'headTilt':
                            formatted_value = f"{float(val):.1f}°" if isinstance(val, (int, float)) else val
                        else:
                            formatted_value = str(val)
                        
                        # Format duration
                        if duration_sec > 0:
                            if duration_sec < 60:
                                duration_str = f"{int(duration_sec)}s"
                            elif duration_sec < 3600:
                                duration_str = f"{int(duration_sec / 60)}m {int(duration_sec % 60)}s"
                            else:
                                hours = int(duration_sec / 3600)
                                minutes = int((duration_sec % 3600) / 60)
                                duration_str = f"{hours}h {minutes}m"
                        else:
                            duration_str = "0s"
                        
                        # Format last update time
                        try:
                            if last_update != 'Never':
                                update_time = datetime.fromisoformat(last_update.rstrip('Z'))
                                now = datetime.utcnow()
                                diff = (now - update_time).total_seconds()
                                if diff < 60:
                                    update_str = "Just now"
                                elif diff < 3600:
                                    update_str = f"{int(diff / 60)}m ago"
                                else:
                                    update_str = f"{int(diff / 3600)}h ago"
                            else:
                                update_str = "Never"
                        except:
                            update_str = "Unknown"
                        
                        formatted_metrics[key] = {
                            'value': formatted_value,
                            'raw': val,
                            'duration': duration_str,
                            'duration_seconds': duration_sec,
                            'last_update': update_str,
                            'last_update_iso': last_update
                        }
                    else:
                        formatted_metrics[key] = {
                            'value': '--',
                            'raw': '--',
                            'duration': '--',
                            'duration_seconds': 0,
                            'last_update': 'Never',
                            'last_update_iso': 'Never'
                        }
                
                # Determine status based on state and metrics
                status = 'offline'
                if is_online:
                    if state == 'DROWSY':
                        status = 'drowsy'
                    elif state == 'ALERT':
                        status = 'alert'
                    elif is_monitoring:
                        status = 'alert'
                    else:
                        status = 'online'
                
                # Calculate time difference for last_active
                if last_active != 'Never':
                    try:
                        last_time = datetime.fromisoformat(last_active.rstrip('Z'))
                        now = datetime.utcnow()
                        diff = now - last_time
                        if diff.total_seconds() < 60:
                            last_active_str = 'Just now'
                        elif diff.total_seconds() < 3600:
                            last_active_str = f'{int(diff.total_seconds() / 60)} min ago'
                        else:
                            last_active_str = f'{int(diff.total_seconds() / 3600)}h ago'
                    except:
                        last_active_str = last_active
                else:
                    last_active_str = 'Never'
                
                driver_info = {
                    'id': email.replace('@', '_').replace('.', '_'),
                    'name': name,
                    'email': email,
                    'status': status,
                    'isOnline': is_online,
                    'isMonitoring': is_monitoring,
                    'lastActive': last_active_str,
                    'metrics': formatted_metrics,
                    'alertCount': session_data.get('alert_count', 0),
                    'sessionTime': session_data.get('session_time', '--')
                }
                
                drivers.append(driver_info)
        
        return jsonify({'ok': True, 'drivers': drivers, 'total': len(drivers)}), 200
        
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.route('/api/driver/heartbeat', methods=['POST'])
def driver_heartbeat():
    """
    Endpoint for drivers to report their status and metrics.
    Should be called periodically to maintain online status.
    """
    try:
        data = request.get_json(silent=True) or {}
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({'ok': False, 'error': 'Email required'}), 400
        
        # Get real-time data from driver's monitor if available
        driver_monitor = get_driver_monitor(email)
        if driver_monitor and driver_monitor.is_running:
            status = driver_monitor.current_status
            metrics = {
                'ear': status.get('ear', '--'),
                'mar': status.get('mar', '--'),
                'perclos': status.get('perclos', '--'),
                'headTilt': status.get('tiltDeg', '--')
            }
            state = status.get('state', 'IDLE')
        else:
            # Use provided data or defaults
            metrics = {
                'ear': data.get('ear', '--'),
                'mar': data.get('mar', '--'),
                'perclos': data.get('perclos', '--'),
                'headTilt': data.get('headTilt', '--')
            }
            state = data.get('state', 'IDLE')
        
        with DRIVER_SESSIONS_LOCK:
            # Get existing session to preserve metric timestamps
            existing_session = DRIVER_SESSIONS.get(email, {})
            existing_metric_times = existing_session.get('metric_times', {})
            
            # Track when each metric was last updated and duration in current state
            now_iso = get_timestamp_iso()
            metric_times = {}
            
            for metric_key in ['ear', 'mar', 'perclos', 'headTilt']:
                current_value = metrics.get(metric_key, '--')
                prev_value = existing_session.get('metrics', {}).get(metric_key, '--')
                prev_time = existing_metric_times.get(metric_key, {}).get('last_update', now_iso)
                
                # If metric value changed, reset timer
                if current_value != prev_value and current_value != '--':
                    metric_times[metric_key] = {
                        'last_update': now_iso,
                        'duration_seconds': 0,
                        'value': current_value,
                        'state_changed': True
                    }
                else:
                    # Calculate duration in current state
                    try:
                        prev_time_obj = datetime.fromisoformat(prev_time.rstrip('Z'))
                        now_obj = datetime.utcnow()
                        duration = (now_obj - prev_time_obj).total_seconds()
                    except:
                        duration = 0
                    
                    metric_times[metric_key] = {
                        'last_update': prev_time if current_value == prev_value else now_iso,
                        'duration_seconds': duration if current_value == prev_value else 0,
                        'value': current_value,
                        'state_changed': current_value != prev_value
                    }
            
            DRIVER_SESSIONS[email] = {
                'is_online': True,
                'is_monitoring': driver_monitor.is_running if driver_monitor else False,
                'last_active': now_iso,
                'state': state,
                'metrics': metrics,
                'metric_times': metric_times,  # Add time tracking
                'alert_count': data.get('alert_count', 0),
                'session_time': data.get('session_time', '--')
            }
        
        return jsonify({'ok': True}), 200
        
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.route('/api/driver/offline', methods=['POST'])
def driver_offline():
    """
    Endpoint for drivers to mark themselves as offline.
    """
    try:
        data = request.get_json(silent=True) or {}
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({'ok': False, 'error': 'Email required'}), 400
        
        with DRIVER_SESSIONS_LOCK:
            if email in DRIVER_SESSIONS:
                DRIVER_SESSIONS[email]['is_online'] = False
                DRIVER_SESSIONS[email]['last_active'] = get_timestamp_iso()
        
        return jsonify({'ok': True}), 200
        
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.route('/camera_settings', methods=['GET'])
def get_camera_settings():
    return jsonify({
        'width': monitor.desired_width,
        'height': monitor.desired_height,
        'fps': monitor.desired_fps,
        'mirror': monitor.mirror_display,
        'jpegQuality': monitor.jpeg_quality,
        'captureIndex': monitor.capture_index,
    }), 200


@app.route('/camera_settings', methods=['POST'])
def update_camera_settings():
    data = request.get_json(silent=True) or {}
    w = data.get('width')
    h = data.get('height')
    fps = data.get('fps')
    mirror = data.get('mirror')
    jpeg_q = data.get('jpegQuality')
    new_index = data.get('captureIndex')
    if isinstance(w, int):
        monitor.desired_width = max(160, min(1920, w))
    if isinstance(h, int):
        monitor.desired_height = max(120, min(1080, h))
    if isinstance(fps, int):
        monitor.desired_fps = max(5, min(60, fps))
    if isinstance(mirror, bool):
        monitor.mirror_display = mirror
    if isinstance(jpeg_q, int):
        monitor.jpeg_quality = max(30, min(95, jpeg_q))
    # Switch camera device if requested
    if isinstance(new_index, int) and 0 <= new_index <= 10 and new_index != monitor.capture_index:
        monitor.capture_index = new_index
        # Reopen camera if running
        if monitor.is_running:
            try:
                if monitor.video_capture:
                    monitor.video_capture.release()
            except Exception:
                pass
            monitor.video_capture = monitor._open_camera_for_indices([monitor.capture_index] + [i for i in range(0, 4) if i != monitor.capture_index])
            if monitor.video_capture and monitor.video_capture.isOpened():
                monitor._apply_capture_properties()
    # Apply to current capture
    monitor._apply_capture_properties()
    return jsonify({'ok': True, 'applied': {
        'width': monitor.desired_width,
        'height': monitor.desired_height,
        'fps': monitor.desired_fps,
        'mirror': monitor.mirror_display,
        'jpegQuality': monitor.jpeg_quality,
        'captureIndex': monitor.capture_index,
    }}), 200


@app.route('/camera_devices', methods=['GET'])
def camera_devices():  # pragma: no cover
    # Probe first few indices; OpenCV lacks enumeration API
    devices = []
    for i in range(0, 6):
        cap = None
        try:
            cap = monitor._open_camera_for_indices([i])
            if cap and cap.isOpened():
                devices.append({'index': i, 'label': f'Camera {i}'})
        except Exception:
            pass
        finally:
            try:
                if cap:
                    cap.release()
            except Exception:
                pass
    # Ensure current index is listed
    if all(d['index'] != monitor.capture_index for d in devices):
        devices.append({'index': monitor.capture_index, 'label': f'Camera {monitor.capture_index}'})
    return jsonify(devices), 200


# -------- Auth endpoints (demo) --------
def _has_admin_account() -> bool:
    """Check if any admin account exists in the system."""
    users = _load_users()
    return any(user.get('role', '').lower() == 'admin' for user in users.values())


# Rate limiting for registration (prevent spam/fake registrations)
REGISTRATION_ATTEMPTS = {}
REGISTRATION_LOCK = threading.Lock()

def check_registration_rate_limit(ip_address: str) -> Tuple[bool, str]:
    """Check if registration attempts exceed rate limit"""
    current_time = time.time()
    with REGISTRATION_LOCK:
        if ip_address not in REGISTRATION_ATTEMPTS:
            REGISTRATION_ATTEMPTS[ip_address] = []
        
        # Remove attempts older than 1 hour
        REGISTRATION_ATTEMPTS[ip_address] = [
            t for t in REGISTRATION_ATTEMPTS[ip_address] 
            if current_time - t < 3600
        ]
        
        # Allow max 3 registrations per hour per IP
        if len(REGISTRATION_ATTEMPTS[ip_address]) >= 3:
            return False, 'Too many registration attempts. Please try again later (max 3 per hour).'
        
        # Record this attempt
        REGISTRATION_ATTEMPTS[ip_address].append(current_time)
        return True, ''

@app.route('/auth/register', methods=['POST'])
def auth_register():
    # SECURITY: Disable public registration - only allow from localhost
    # This prevents unauthorized users from registering through public URLs
    if request.remote_addr != '127.0.0.1' and request.remote_addr != '::1':
        return jsonify({'ok': False, 'error': 'Registration disabled. Please contact administrator.'}), 403
    
    # Rate limiting: prevent spam/fake registrations
    ip_address = request.remote_addr or 'unknown'
    can_register, rate_limit_msg = check_registration_rate_limit(ip_address)
    if not can_register:
        return jsonify({'ok': False, 'error': rate_limit_msg}), 429
    
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    requested_role = (data.get('role') or 'driver').strip().lower()
    
    if not email or not password:
        return jsonify({'ok': False, 'error': 'Email and password required'}), 400
    
    # Basic email validation
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return jsonify({'ok': False, 'error': 'Invalid email format'}), 400
    
    users = _load_users()
    if email in users:
        return jsonify({'ok': False, 'error': 'Account exists'}), 409
    
    # SINGLE ADMIN ENFORCEMENT: Prevent admin account creation through registration
    # Admin accounts cannot be created via registration - they must be manually created
    if requested_role == 'admin':
        return jsonify({
            'ok': False, 
            'error': 'Admin accounts cannot be created through registration. Only one admin account exists. Please contact the system administrator.'
        }), 403
    
    # Check if admin already exists - if not, allow first user to become admin (one-time setup)
    has_admin = _has_admin_account()
    if not has_admin and len(users) == 0:
        # First user becomes admin (one-time setup only)
        role = 'admin'
    else:
        # All subsequent registrations are drivers only
        role = 'driver'
    
    # Create user account
    user_data = {
        'passwordHash': generate_password_hash(password),
        'role': role,
        'name': (data.get('name') or '').strip()
    }
    
    users[email] = user_data
    _save_users(users)
    
    return jsonify({
        'ok': True,
        'role': role
    }), 201


@app.route('/auth/login', methods=['POST'])
def auth_login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    users = _load_users()
    user = users.get(email)
    if not user or not check_password_hash(user.get('passwordHash', ''), password):
        return jsonify({'ok': False, 'error': 'Invalid credentials'}), 401
    # Enforce admin via env override; persist if changed
    role = user.get('role')
    expected_role = 'admin' if _is_admin_email(email) else (role or 'user')
    if role != expected_role:
        try:
            users[email]['role'] = expected_role
            _save_users(users)
        except Exception:
            pass
    token = create_token(email)
    return jsonify({'ok': True, 'token': token, 'email': email, 'role': expected_role}), 200


@app.route('/ack', methods=['POST'])
def ack_alert():
    # Acknowledge alert (no snooze)
    monitor._send_iot_command('SAFE')
    try:
        event = {
            'time': get_timestamp_iso(),
            'type': 'AlertAcknowledged',
            'confidence': None,
            'notes': 'User acknowledged alert',
        }
        monitor._append_event(event)
    except Exception:
        pass
    return jsonify({'ok': True}), 200


# Client location (optional) to enrich SMS with map link
@app.route('/location', methods=['POST'])
def set_location():
    data = request.get_json(silent=True) or {}
    try:
        lat = float(data.get('lat'))
        lon = float(data.get('lon'))
    except Exception:
        return jsonify({'ok': False, 'error': 'lat/lon required'}), 400
    acc = data.get('accuracy')
    monitor.last_location = {
        'lat': lat,
        'lon': lon,
        'accuracy': float(acc) if isinstance(acc, (int, float, str)) else None,
        'time': get_timestamp_iso(),
    }
    return jsonify({'ok': True}), 200


@app.route('/location', methods=['GET'])
def get_location():
    return jsonify(monitor.last_location or {}), 200


@app.route('/process_frame', methods=['POST'])
def process_frame():
    """
    Process a single frame from browser camera for drowsiness detection.
    Accepts base64 encoded image and returns detection results.
    """
    try:
        data = request.get_json(silent=True) or {}
        frame_data = data.get('frame')
        driver_email = data.get('driver_email', '').strip().lower()
        
        if not frame_data:
            return jsonify({'ok': False, 'error': 'No frame data'}), 400
        
        # Get the appropriate monitor instance
        if driver_email:
            driver_monitor = get_or_create_driver_monitor(driver_email)
        else:
            driver_monitor = monitor
        
        # Ensure face mesh is initialized
        driver_monitor._ensure_facemesh()
        
        # Decode base64 image
        import base64
        try:
            # Remove data URL prefix if present
            if ',' in frame_data:
                frame_data = frame_data.split(',')[1]
            img_bytes = base64.b64decode(frame_data)
            nparr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError('Failed to decode image')
        except Exception as e:
            return jsonify({'ok': False, 'error': f'Invalid image data: {str(e)}'}), 400
        
        # Process frame with MediaPipe
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = driver_monitor.face_mesh.process(rgb)
        
        ear_value = None
        mar_value = None
        tilt_deg = None
        state = 'ALERT'
        confidence = None
        reason = None
        
        if results.multi_face_landmarks:
            h, w = frame.shape[:2]
            face_landmarks = results.multi_face_landmarks[0]
            pts = np.array([[lm.x * w, lm.y * h] for lm in face_landmarks.landmark], dtype=np.float32)
            
            try:
                ear_value = driver_monitor._eye_aspect_ratio_from_landmarks(pts)
                mar_value = driver_monitor._mouth_aspect_ratio(pts)
                tilt_deg = driver_monitor._eye_line_tilt_deg(pts)
                
                # Update counters and metric time tracking
                ear_in_alert = ear_value < driver_monitor.ear_threshold
                if ear_in_alert:
                    driver_monitor._consec_below += 1
                    driver_monitor.perclos_window.append(1)
                else:
                    driver_monitor._consec_below = 0
                    driver_monitor.perclos_window.append(0)
                driver_monitor._update_metric_time('ear', ear_in_alert, ear_value)
                
                mar_in_alert = mar_value > driver_monitor.mar_threshold
                if mar_in_alert:
                    driver_monitor._consec_yawn += 1
                else:
                    driver_monitor._consec_yawn = 0
                driver_monitor._update_metric_time('mar', mar_in_alert, mar_value)
                
                tilt_in_alert = tilt_deg > driver_monitor.tilt_threshold_deg
                if tilt_in_alert:
                    driver_monitor._consec_tilt += 1
                else:
                    driver_monitor._consec_tilt = 0
                driver_monitor._update_metric_time('headTilt', tilt_in_alert, tilt_deg)
                
                # Calculate PERCLOS BEFORE state determination (needed for detection)
                perclos = None
                if len(driver_monitor.perclos_window) > 0:
                    try:
                        perclos = float(sum(driver_monitor.perclos_window)) / float(len(driver_monitor.perclos_window))
                        driver_monitor.perclos = perclos
                    except Exception:
                        pass
                
                # Update PERCLOS metric time tracking
                perclos_in_alert = perclos is not None and perclos > driver_monitor.perclos_threshold
                driver_monitor._update_metric_time('perclos', perclos_in_alert, perclos)
                
                # Determine state
                drowsy_eyes = driver_monitor._consec_below >= driver_monitor.frames_below_threshold_required
                # More sensitive yawning detection - reduced from 6 to 4 frames
                drowsy_yawn = driver_monitor._consec_yawn >= max(4, driver_monitor.frames_below_threshold_required // 3)
                drowsy_tilt = driver_monitor._consec_tilt >= max(6, driver_monitor.frames_below_threshold_required // 2)
                
                # Check metric timer thresholds (optimized for faster detection)
                with METRIC_TIMERS_LOCK:
                    ear_timer = METRIC_TIMERS.get('ear_threshold_duration', 2)  # Reduced default
                    mar_timer = METRIC_TIMERS.get('mar_threshold_duration', 1)  # Reduced default
                    tilt_timer = METRIC_TIMERS.get('tilt_threshold_duration', 1)  # Reduced default
                    perclos_timer = METRIC_TIMERS.get('perclos_threshold_duration', 2)  # Reduced default
                
                # Get metric time data
                ear_time_data = driver_monitor._get_metric_time_data('ear')
                mar_time_data = driver_monitor._get_metric_time_data('mar')
                tilt_time_data = driver_monitor._get_metric_time_data('headTilt')
                perclos_time_data = driver_monitor._get_metric_time_data('perclos')
                
                # Check if metric has been in alert state long enough
                ear_timer_triggered = ear_in_alert and ear_time_data['duration_seconds'] >= ear_timer
                mar_timer_triggered = mar_in_alert and mar_time_data['duration_seconds'] >= mar_timer
                tilt_timer_triggered = tilt_in_alert and tilt_time_data['duration_seconds'] >= tilt_timer
                perclos_timer_triggered = perclos_in_alert and perclos_time_data['duration_seconds'] >= perclos_timer
                
                # STRICT detection: Require BOTH timer AND consecutive frames to reduce false positives
                # Only trigger if BOTH conditions are met (timer threshold AND minimum consecutive frames)
                # This prevents false positives from brief eye closures or detection glitches
                drowsy_eyes = drowsy_eyes and ear_timer_triggered and (driver_monitor._consec_below >= driver_monitor.frames_below_threshold_required)
                # For yawning and tilt, require timer AND high consecutive frames (very strict)
                drowsy_yawn = (drowsy_yawn and mar_timer_triggered) or (driver_monitor._consec_yawn >= 20)  # Increased to 20 for strict detection
                drowsy_tilt = (drowsy_tilt and tilt_timer_triggered) or (driver_monitor._consec_tilt >= 25)  # Increased to 25 for strict detection
                # PERCLOS requires timer AND must be significantly above threshold (more reliable)
                drowsy_perclos = perclos_timer_triggered and (perclos_in_alert and (perclos or 0) > (driver_monitor.perclos_threshold * 1.2))  # 20% above threshold
                
                if drowsy_eyes or drowsy_yawn or drowsy_tilt or drowsy_perclos:
                    state = 'DROWSY'
                    if drowsy_eyes:
                        reason = 'eyes closed (EAR)'
                        confidence = min(1.0, max(0.0, (driver_monitor.ear_threshold - ear_value) / max(0.15, driver_monitor.ear_threshold)))
                    elif drowsy_yawn:
                        reason = 'yawning (MAR)'
                        confidence = min(1.0, max(0.0, (mar_value - driver_monitor.mar_threshold) / max(0.4, driver_monitor.mar_threshold)))
                    elif drowsy_tilt:
                        reason = 'head tilt'
                        confidence = min(1.0, max(0.0, (tilt_deg - driver_monitor.tilt_threshold_deg) / max(20.0, driver_monitor.tilt_threshold_deg)))
                    elif drowsy_perclos:
                        reason = 'high PERCLOS (prolonged eye closure)'
                        confidence = min(1.0, max(0.0, ((driver_monitor.perclos or driver_monitor.perclos_threshold) - driver_monitor.perclos_threshold) / 0.3))
                else:
                    state = 'ALERT'
                    confidence = 1.0
                    
            except Exception as e:
                return jsonify({'ok': False, 'error': f'Processing error: {str(e)}'}), 500
        
        # PERCLOS is now calculated and checked above with other metrics in the main detection block
        # Get perclos value from monitor if it was calculated
        perclos = getattr(driver_monitor, 'perclos', None)
        
        # Update current status
        now_iso = get_timestamp_iso()
        driver_monitor.current_status = {
            'state': state,
            'ear': ear_value,
            'mar': mar_value,
            'tiltDeg': tilt_deg,
            'perclos': perclos,
            'confidence': confidence,
            'timestamp': now_iso,
            'running': True,
            'reason': reason,
            'metric_times': {
                'ear': driver_monitor._get_metric_time_data('ear'),
                'mar': driver_monitor._get_metric_time_data('mar'),
                'headTilt': driver_monitor._get_metric_time_data('headTilt'),
                'perclos': driver_monitor._get_metric_time_data('perclos')
            }
        }
        
        # Send Arduino command - always send to ensure sync (browser cam processes less frequently)
        # Force send command immediately for browser camera (processes at lower frequency)
        try:
            if state == 'DROWSY':
                driver_monitor._send_iot_command('ALERT')
            else:
                driver_monitor._send_iot_command('SAFE')
        except Exception:
            # Arduino command failed - continue anyway (Arduino is optional)
            pass
        
        return jsonify({
            'ok': True,
            'state': state,
            'ear': ear_value,
            'mar': mar_value,
            'tiltDeg': tilt_deg,
            'perclos': perclos,
            'confidence': confidence,
            'reason': reason,
            'timestamp': now_iso,
            'metric_times': driver_monitor.current_status.get('metric_times', {})
        }), 200
        
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    port = int(os.getenv('FLASK_PORT', '5000'))
    app.run(host=host, port=port, debug=True, threaded=True)


