// Toggle mobile sidebar
const sidebarMobile = document.getElementById('sidebarMobile');
const sidebarCollapseBtn = document.getElementById('sidebarCollapseBtn');
const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');

sidebarCollapseBtn?.addEventListener('click', () => {
  if (sidebarMobile) sidebarMobile.classList.remove('-translate-x-full');
});
sidebarCloseBtn?.addEventListener('click', () => {
  if (sidebarMobile) sidebarMobile.classList.add('-translate-x-full');
});

// Update timestamps for camera feed and driver status every second
const cameraTimestampEl = document.getElementById('cameraTimestamp');
const driverStatusUpdatedEl = document.getElementById('driverStatusUpdated');
let isMonitoringRunning = false;

function updateTimestamps() {
  const now = new Date();
  const dateTimeStr = now.toLocaleString('en-US', { hour12: false });
  if (cameraTimestampEl) cameraTimestampEl.textContent = isMonitoringRunning ? dateTimeStr : '--/--/-- --:--:--';
  if (driverStatusUpdatedEl) driverStatusUpdatedEl.textContent = 'Last updated: ' + dateTimeStr;
}
updateTimestamps();
setInterval(updateTimestamps, 1000);

// Animate button icon on hover - toggled start/done
const startBtn = document.getElementById('startMonitoringBtn');
if (startBtn) {
  startBtn.addEventListener('click', () => {
    const running = startBtn.dataset.running === 'true';
    const endpoint = running ? '/stop' : '/start';
    const email = localStorage.getItem('email') || '';

    // Disable button to prevent double-clicks
    startBtn.disabled = true;
    const originalHTML = startBtn.innerHTML;
    startBtn.innerHTML = '<svg class="w-5 h-5 shrink-0 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg><span>Processing...</span>';

    fetch(`${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ driver_email: email })
    })
      .then(async r => {
        let data = null; try { data = await r.json(); } catch (e) { }
        if (!r.ok || !data || data.ok !== true) {
          const txt = data && data.error ? data.error : 'Unknown error';
          throw new Error(txt);
        }
        return data;
      })
      .then(() => {
        // On first start click, resume audio context (user gesture)
        try { if (typeof audioCtx !== 'undefined' && audioCtx && audioCtx.state === 'suspended') audioCtx.resume(); } catch (e) { }
        if (!running) {
          monitoringStartTime = Date.now();
        } else {
          monitoringStartTime = null;
        }
        updateRunningUI(!running);
      })
      .catch((err) => {
        alert((running ? 'Failed to stop monitoring' : 'Failed to start monitoring') + (err && err.message ? `: ${err.message}` : '. Is the camera free and backend running?'));
        // Restore button on error
        startBtn.innerHTML = originalHTML;
      })
      .finally(() => {
        // Re-enable button
        startBtn.disabled = false;
      });
  });
}

function updateRunningUI(isRunning) {
  const btn = document.getElementById('startMonitoringBtn');
  const video = document.getElementById('videoFeed');
  if (!btn) return;
  btn.dataset.running = isRunning ? 'true' : 'false';
  isMonitoringRunning = !!isRunning;

  // Reset alert count when monitoring starts
  if (isRunning) {
    resetAlertCount();
    // Reset alert showing state
    window.alertCurrentlyShowing = false;
  } else {
    // Monitoring stopped - hide alert and reset state
    if (alertOverlay) alertOverlay.classList.add('hidden');
    window.alertCurrentlyShowing = false;
    playAlarm(false);
  }

  if (isRunning) {
    btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 18L18 6M6 6l12 12"/></svg><span>Stop Monitoring</span>';
    btn.classList.replace('bg-blue-600', 'bg-red-600');
    btn.classList.replace('hover:bg-blue-700', 'hover:bg-red-700');
    const placeholder = document.getElementById('videoPlaceholder');
    if (placeholder) placeholder.classList.add('hidden');

    // Handle browser camera processing
    if (browserCam && !browserCam.classList.contains('hidden')) {
      // Browser camera is active, start processing frames
      startBrowserCamProcessing();
    } else if (video) {
      // Use server camera feed with driver-specific endpoint
      const email = localStorage.getItem('email') || '';
      const feedUrl = email ? `/video_feed/${encodeURIComponent(email)}` : '/video_feed';
      
      // Show video element
      video.style.display = 'block';
      const placeholder = document.getElementById('videoPlaceholder');
      if (placeholder) placeholder.classList.add('hidden');
      
      // Optimize image loading for MJPEG stream
      video.loading = 'eager';
      video.decoding = 'async';
      video.fetchPriority = 'high';
      
      // Set up error handling with throttling
      let errorCount = 0;
      const maxErrors = 3;
      let lastErrorTime = 0;
      
      video.onerror = () => {
        const now = Date.now();
        // Throttle error handling (max once per 2 seconds)
        if (now - lastErrorTime < 2000) return;
        lastErrorTime = now;
        
        errorCount++;
        if (errorCount >= maxErrors) {
          // After multiple errors, show placeholder
          if (placeholder) placeholder.classList.remove('hidden');
          video.style.display = 'none';
          errorCount = 0; // Reset for retry
        } else {
          // Retry loading after a short delay
          setTimeout(() => {
            // Add cache busting only on retry
            video.src = feedUrl + '?t=' + Date.now();
          }, 1000);
        }
      };
      
      video.onload = () => {
        // Video loaded successfully
        errorCount = 0;
        if (placeholder) placeholder.classList.add('hidden');
        video.style.display = 'block';
      };
      
      // Set source and start loading (no cache busting on initial load for better performance)
      video.src = feedUrl;
    }
  } else {
    btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 shrink-0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.752 11.168l-6.814 3.905A.75.75 0 017 14.256v-7.5a.75.75 0 011.127-.66l6.814 3.905a.75.75 0 010 1.296z"/></svg><span>Start Monitoring</span>';
    btn.classList.replace('bg-red-600', 'bg-blue-600');
    btn.classList.replace('hover:bg-red-700', 'hover:bg-blue-700');
    const placeholder = document.getElementById('videoPlaceholder');
    if (placeholder) placeholder.classList.remove('hidden');

    // Stop browser camera processing
    stopBrowserCamProcessing();

    if (video) {
      video.removeAttribute('src');
      // Force reload placeholder gray background
      video.src = '';
    }
  }
}

// Login: call backend auth and show/hide password
const loginForm = document.getElementById('loginForm');
const togglePassword = document.getElementById('togglePassword');
const loginPassword = document.getElementById('loginPassword');
if (loginForm) {
  loginForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const email = document.getElementById('loginUsername')?.value?.trim();
    const pass = document.getElementById('loginPassword')?.value;
    fetch('/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password: pass })
    }).then(r => r.json()).then(res => {
      if (!res.ok) { alert(res.error || 'Login failed'); return; }
      localStorage.setItem('token', res.token);
      localStorage.setItem('email', res.email);
      if (res.role) localStorage.setItem('role', res.role);
      // Redirect to admin or driver dashboard based on role
      const userRole = (res.role || 'user').toLowerCase();
      if (userRole === 'admin') {
        window.location.href = 'admin.html';
      } else {
        window.location.href = 'driver.html';
      }
    }).catch(() => alert('Login failed'));
  });
}
// Register page -> call backend
const registerForm = document.getElementById('registerForm');
if (registerForm) {
  registerForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const email = document.getElementById('regEmail')?.value?.trim();
    const pass = document.getElementById('regPassword')?.value;
    fetch('/auth/register', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password: pass })
    }).then(r => r.json()).then(res => {
      if (!res.ok) { alert(res.error || 'Registration failed'); return; }
      alert('Registered successfully. Please log in.');
      window.location.href = 'login.html';
    }).catch(() => alert('Registration failed'));
  });
}
if (togglePassword && loginPassword) {
  togglePassword.addEventListener('click', () => {
    const isPassword = loginPassword.getAttribute('type') === 'password';
    loginPassword.setAttribute('type', isPassword ? 'text' : 'password');
  });
}

// Logout: return to appropriate login page based on role
const logoutBtn = document.getElementById('logoutBtn');
if (logoutBtn) {
  logoutBtn.addEventListener('click', () => {
    try {
      const role = (localStorage.getItem('role') || 'user').toLowerCase();
      localStorage.removeItem('token');
      localStorage.removeItem('email');
      localStorage.removeItem('role');
      // Redirect to login page
      window.location.href = 'login.html';
    } catch (e) {
      window.location.href = 'login.html';
    }
  });
}
const logoutBtn2 = document.getElementById('logoutBtn2');
if (logoutBtn2) {
  logoutBtn2.addEventListener('click', () => {
    try {
      localStorage.removeItem('token');
      localStorage.removeItem('email');
    } catch (e) { }
    window.location.href = 'login.html';
  });
}

// Auth guard per flow: redirect to login if not authenticated
function requireAuth() {
  const publicPages = ['login.html', 'register.html'];
  const isPublic = publicPages.some(p => location.pathname.endsWith(p));
  const token = localStorage.getItem('token');
  if (!isPublic && !token) {
    window.location.href = 'login.html';
  }
}
requireAuth();

// Role-based UI tweaks (hide admin-only cards for non-admin and role-specific navigation)
function applyRoleUI() {
  const role = (localStorage.getItem('role') || 'user').toLowerCase();
  const adminCard = document.getElementById('adminLocationCard');
  if (adminCard) adminCard.classList.toggle('hidden', role !== 'admin');

  // Show/hide navigation links based on role
  const adminLink = document.getElementById('adminLink');
  const driverLink = document.getElementById('driverLink');
  if (role === 'admin') {
    // Admin sees only admin panel link, not driver link
    if (driverLink) driverLink.classList.add('hidden');
    if (adminLink) adminLink.classList.remove('hidden');
  } else {
    // Driver sees only driver link, not admin link
    if (adminLink) adminLink.classList.add('hidden');
    if (driverLink) driverLink.classList.remove('hidden');
  }
}
applyRoleUI();

// User avatar initial from email
const userAvatarInitial = document.getElementById('userAvatarInitial');
if (userAvatarInitial) {
  try {
    const email = localStorage.getItem('email') || '';
    const initial = email.trim() ? (email.trim()[0] || 'U') : 'U';
    userAvatarInitial.textContent = initial.toUpperCase();
  } catch (e) { }
}
// Settings: sensitivity slider label update
const sensitivityRange = document.getElementById('sensitivityRange');
const sensitivityLabel = document.getElementById('sensitivityLabel');
if (sensitivityRange && sensitivityLabel) {
  const updateSensitivityLabel = () => {
    const value = Number(sensitivityRange.value);
    let label = 'Normal';
    if (value < 34) label = 'Low';
    else if (value > 66) label = 'High';
    else label = 'Normal';
    sensitivityLabel.textContent = label;
    // push to backend
    fetch('/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sensitivity: value })
    }).catch(() => { });
  };
  sensitivityRange.addEventListener('input', updateSensitivityLabel);
  updateSensitivityLabel();
}

// Settings: demo add contact button shows a hint
const addContactBtn = document.getElementById('addContactBtn');
const contactHint = document.getElementById('contactHint');
if (addContactBtn && contactHint) {
  addContactBtn.addEventListener('click', () => {
    contactHint.classList.remove('hidden');
    setTimeout(() => contactHint.classList.add('hidden'), 2000);
  });
}

// Status polling and history loader
const driverStatusState = document.getElementById('driverStatusState');
const driverStatusMessage = document.getElementById('driverStatusMessage');
const alertOverlay = document.getElementById('alertOverlay');
const alertReason = document.getElementById('alertReason');
const ackAlertBtn = document.getElementById('ackAlertBtn');
// Metrics elements
const metricEAR = document.getElementById('metricEAR');
const metricMAR = document.getElementById('metricMAR');
const metricTilt = document.getElementById('metricTilt');
const metricPerclos = document.getElementById('metricPerclos');
// Browser camera elements
const browserCam = document.getElementById('browserCam');
const toggleBrowserCam = document.getElementById('toggleBrowserCam');
let browserCamStream;
let browserCamProcessingInterval = null;

let audioCtx; let alarmOsc; let alarmGain;
let lastStateForEvents;
let driverHeartbeatInterval = null;
let monitoringStartTime = null;
let totalAlertCount = 0;

// Driver heartbeat - send status to backend every 3 seconds
function startDriverHeartbeat() {
  if (driverHeartbeatInterval) return;

  const email = localStorage.getItem('email');
  if (!email) return;

  const role = (localStorage.getItem('role') || 'user').toLowerCase();
  if (role === 'admin') return; // Admins don't send heartbeats

  driverHeartbeatInterval = setInterval(() => {
    const currentStatus = getCurrentMonitoringStatus();
    fetch('/api/driver/heartbeat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email,
        ear: currentStatus.ear,
        mar: currentStatus.mar,
        perclos: currentStatus.perclos,
        headTilt: currentStatus.headTilt,
        state: currentStatus.state,
        alert_count: totalAlertCount,
        session_time: currentStatus.sessionTime
      })
    }).catch(() => { });
  }, 3000);
}

function stopDriverHeartbeat() {
  if (driverHeartbeatInterval) {
    clearInterval(driverHeartbeatInterval);
    driverHeartbeatInterval = null;

    // Mark as offline
    const email = localStorage.getItem('email');
    if (email) {
      fetch('/api/driver/offline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email })
      }).catch(() => { });
    }
  }
}

function getCurrentMonitoringStatus() {
  const ear = metricEAR?.textContent || '--';
  const mar = metricMAR?.textContent || '--';
  const perclos = metricPerclos?.textContent || '--';
  const headTilt = metricTilt?.textContent?.replace('°', '') || '--';
  const state = driverStatusState?.textContent || 'IDLE';

  let sessionTime = '--';
  if (monitoringStartTime && isMonitoringRunning) {
    const elapsed = Date.now() - monitoringStartTime;
    const hours = Math.floor(elapsed / 3600000);
    const minutes = Math.floor((elapsed % 3600000) / 60000);
    sessionTime = `${hours}h ${minutes}m`;
  }

  return { ear, mar, perclos, headTilt, state, sessionTime };
}

// Start heartbeat when driver logs in
const role = (localStorage.getItem('role') || 'user').toLowerCase();
if (role !== 'admin') {
  startDriverHeartbeat();
}

// Stop heartbeat on page unload
window.addEventListener('beforeunload', () => {
  stopDriverHeartbeat();
});

function ensureAudio() {
  if (audioCtx) return;
  try {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    alarmOsc = audioCtx.createOscillator();
    alarmGain = audioCtx.createGain();
    alarmOsc.type = 'square';
    alarmOsc.frequency.value = 800; // Hz
    alarmGain.gain.value = 0;
    alarmOsc.connect(alarmGain).connect(audioCtx.destination);
    alarmOsc.start();
  } catch (e) { /* noop */ }
}
function playAlarm(on) {
  ensureAudio();
  if (!alarmGain) return;
  alarmGain.gain.value = on ? 0.2 : 0.0;
}
function vibrate(ms) {
  if (navigator.vibrate) navigator.vibrate(ms);
}
function notify(msg) {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'granted') new Notification(msg);
}
function requestNotifyPermission() {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'default') Notification.requestPermission();
}
requestNotifyPermission();
// Helper function to format metric time information
function updateMetricTime(metricName, metricTimeData, timeElId, durationElId) {
  const timeEl = document.getElementById(timeElId);
  const durationEl = durationElId ? document.getElementById(durationElId) : null;

  if (!timeEl) return;

  if (!metricTimeData || metricTimeData.last_update === 'Never' || metricTimeData.last_update === undefined) {
    timeEl.textContent = 'Never updated';
    if (durationEl) durationEl.textContent = '';
    return;
  }

  try {
    // Format last update time
    const updateTime = new Date(metricTimeData.last_update);
    const now = new Date();
    const diffSeconds = Math.floor((now - updateTime) / 1000);

    let timeStr = '';
    if (diffSeconds < 5) {
      timeStr = 'Just now';
    } else if (diffSeconds < 60) {
      timeStr = `${diffSeconds}s ago`;
    } else if (diffSeconds < 3600) {
      const minutes = Math.floor(diffSeconds / 60);
      timeStr = `${minutes}m ago`;
    } else {
      const hours = Math.floor(diffSeconds / 3600);
      timeStr = `${hours}h ago`;
    }

    timeEl.textContent = timeStr;

    // Format duration in current state (only if durationEl is provided)
    if (durationEl) {
      const durationSeconds = metricTimeData.duration_seconds || 0;
      let durationStr = '';
      if (durationSeconds < 60) {
        durationStr = `Duration: ${Math.floor(durationSeconds)}s`;
      } else if (durationSeconds < 3600) {
        const minutes = Math.floor(durationSeconds / 60);
        const seconds = Math.floor(durationSeconds % 60);
        durationStr = `Duration: ${minutes}m ${seconds}s`;
      } else {
        const hours = Math.floor(durationSeconds / 3600);
        const minutes = Math.floor((durationSeconds % 3600) / 60);
        durationStr = `Duration: ${hours}h ${minutes}m`;
      }
      durationEl.textContent = durationStr;
    }
  } catch (e) {
    timeEl.textContent = '--';
    if (durationEl) durationEl.textContent = '';
  }
}

// Helper function to update threshold progress bars
function updateMetricThresholdProgress(metricName, metricTimeData, thresholdSeconds, currentValue, valueThreshold, thresholdElId, progressElId, progressTextElId) {
  const thresholdEl = document.getElementById(thresholdElId);
  const progressEl = document.getElementById(progressElId);
  const progressTextEl = document.getElementById(progressTextElId);

  if (!thresholdEl || !progressEl || !progressTextEl) return;

  // Update threshold display
  thresholdEl.textContent = `${thresholdSeconds}s`;

  // Check if metric is in alert state (below/above threshold depending on metric)
  let isInAlertState = false;
  if (currentValue !== null && currentValue !== undefined && currentValue !== '--' && typeof currentValue === 'number') {
    if (metricName === 'EAR') {
      isInAlertState = currentValue < valueThreshold; // EAR below threshold = drowsy
    } else if (metricName === 'MAR') {
      isInAlertState = currentValue > valueThreshold; // MAR above threshold = yawning
    } else if (metricName === 'Tilt') {
      isInAlertState = currentValue > valueThreshold; // Tilt above threshold = drowsy
    } else if (metricName === 'PERCLOS') {
      // PERCLOS is a percentage (0-1), check if above threshold
      const perclosValue = typeof currentValue === 'number' ? currentValue : (typeof currentValue === 'string' ? parseFloat(currentValue.replace('%', '')) / 100 : 0);
      isInAlertState = perclosValue > valueThreshold; // PERCLOS above threshold = drowsy
    }
  }

  // Also check if the metric time data indicates it's in alert state
  // The duration_seconds should only be tracked when metric is in alert state
  const durationSeconds = metricTimeData?.duration_seconds || 0;
  const hasDuration = durationSeconds > 0;

  if (!isInAlertState && !hasDuration) {
    // Not in alert state and no duration tracked
    progressEl.style.width = '0%';
    progressEl.className = 'bg-gray-300 h-1.5 rounded-full transition-all duration-300';
    progressTextEl.textContent = 'Normal';
    progressTextEl.className = 'text-xs text-gray-600 mt-0.5';
    return;
  }

  // If in alert state or has duration, show progress
  // Use duration if available, otherwise start from 0
  const activeDuration = hasDuration ? durationSeconds : 0;
  const progressPercent = Math.min(100, (activeDuration / thresholdSeconds) * 100);

  // Update progress bar width
  progressEl.style.width = `${progressPercent}%`;

  // Change color based on progress (green -> yellow -> red)
  if (progressPercent < 30) {
    progressEl.className = 'bg-green-500 h-1.5 rounded-full transition-all duration-300';
  } else if (progressPercent < 70) {
    progressEl.className = 'bg-yellow-500 h-1.5 rounded-full transition-all duration-300';
  } else {
    progressEl.className = 'bg-red-500 h-1.5 rounded-full transition-all duration-300';
  }

  // Update progress text
  const remainingSeconds = Math.max(0, thresholdSeconds - activeDuration);
  if (progressPercent >= 100) {
    progressTextEl.textContent = 'Alert will trigger';
    progressTextEl.className = 'text-xs text-red-600 font-semibold mt-0.5';
  } else if (remainingSeconds <= 2) {
    progressTextEl.textContent = `${remainingSeconds.toFixed(1)}s until alert`;
    progressTextEl.className = 'text-xs text-red-600 font-semibold mt-0.5';
  } else if (remainingSeconds <= thresholdSeconds * 0.3) {
    progressTextEl.textContent = `${Math.ceil(remainingSeconds)}s remaining`;
    progressTextEl.className = 'text-xs text-amber-600 font-medium mt-0.5';
  } else if (isInAlertState || hasDuration) {
    progressTextEl.textContent = `${Math.ceil(remainingSeconds)}s remaining`;
    progressTextEl.className = 'text-xs text-gray-600 mt-0.5';
  } else {
    progressTextEl.textContent = 'Normal';
    progressTextEl.className = 'text-xs text-gray-600 mt-0.5';
  }
}

function pollStatus() {
  const email = localStorage.getItem('email');
  const statusUrl = email ? `/status?driver=${encodeURIComponent(email)}` : '/status';

  fetch(statusUrl).then(r => r.json()).then(s => {
    if (driverStatusState && driverStatusMessage) {
      const state = s.state || 'IDLE';
      isMonitoringRunning = !!s.running;

      // Track alert count
      if (state === 'DROWSY' && lastStateForEvents !== 'DROWSY') {
        totalAlertCount++;
      }

      driverStatusState.textContent = state === 'DROWSY' ? 'Drowsy' : (state === 'ALERT' ? 'Alert' : 'Idle');
      driverStatusState.classList.toggle('text-green-600', state === 'ALERT');
      driverStatusState.classList.toggle('text-red-600', state === 'DROWSY');
      driverStatusMessage.textContent = state === 'DROWSY' ? 'Drowsiness detected' : (state === 'ALERT' ? 'Driver is alert and focused' : 'System idle');
      // Update driver status icon visuals
      const icon = document.getElementById('driverStatusIcon');
      const wrap = document.getElementById('driverStatusIconWrap');
      if (icon && wrap) {
        if (state === 'DROWSY') {
          icon.className = 'ph ph-warning-circle text-red-600 text-4xl leading-none';
          wrap.className = 'w-20 h-20 rounded-full bg-red-100 flex items-center justify-center mb-3 border border-red-300';
        } else if (state === 'ALERT') {
          icon.className = 'ph ph-check-circle text-green-600 text-4xl leading-none';
          wrap.className = 'w-20 h-20 rounded-full bg-green-100 flex items-center justify-center mb-3 border border-green-300';
        } else {
          icon.className = 'ph ph-moon text-gray-500 text-4xl leading-none';
          wrap.className = 'w-20 h-20 rounded-full bg-gray-100 flex items-center justify-center mb-3 border border-gray-300';
        }
      }
      updateRunningUI(!!s.running);
      if (eventsTableBody && state !== lastStateForEvents) {
        lastStateForEvents = state;
        // Refresh history immediately on state change
        try { loadEvents(); } catch (e) { }
      }
    }
    // Update metrics
    if (metricEAR) metricEAR.textContent = typeof s.ear === 'number' ? s.ear.toFixed(3) : '--';
    if (metricMAR) metricMAR.textContent = typeof s.mar === 'number' ? s.mar.toFixed(3) : '--';
    if (metricTilt) metricTilt.textContent = typeof s.tiltDeg === 'number' ? s.tiltDeg.toFixed(1) + '°' : '--';
    if (metricPerclos) metricPerclos.textContent = typeof s.perclos === 'number' ? Math.round(s.perclos * 100) + '%' : '--';

    // Update metric times if available
    if (s.metric_times) {
      updateMetricTime('EAR', s.metric_times.ear, 'metricEARTime', null);
      updateMetricTime('MAR', s.metric_times.mar, 'metricMARTime', null);
      updateMetricTime('Tilt', s.metric_times.headTilt, 'metricTiltTime', null);
      updateMetricTime('PERCLOS', s.metric_times.perclos, 'metricPerclosTime', null);
    } else {
      // Clear time displays if no metric times available
      ['metricEARTime', 'metricMARTime', 'metricTiltTime', 'metricPerclosTime'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '--';
      });
    }

    // Update threshold progress bars if metric timers are available
    if (s.metric_timers && s.value_thresholds) {
      updateMetricThresholdProgress('EAR', s.metric_times?.ear, s.metric_timers.ear, s.ear, s.value_thresholds.ear, 'metricEARThreshold', 'metricEARProgress', 'metricEARProgressText');
      updateMetricThresholdProgress('MAR', s.metric_times?.mar, s.metric_timers.mar, s.mar, s.value_thresholds.mar, 'metricMARThreshold', 'metricMARProgress', 'metricMARProgressText');
      updateMetricThresholdProgress('Tilt', s.metric_times?.headTilt, s.metric_timers.tilt, s.tiltDeg, s.value_thresholds.tilt, 'metricTiltThreshold', 'metricTiltProgress', 'metricTiltProgressText');
      updateMetricThresholdProgress('PERCLOS', s.metric_times?.perclos, s.metric_timers.perclos, s.perclos, s.value_thresholds.perclos, 'metricPerclosThreshold', 'metricPerclosProgress', 'metricPerclosProgressText');
    } else {
      // Clear threshold displays
      ['metricEARThreshold', 'metricMARThreshold', 'metricTiltThreshold', 'metricPerclosThreshold'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '--';
      });
      ['metricEARProgress', 'metricMARProgress', 'metricTiltProgress', 'metricPerclosProgress'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.width = '0%';
      });
      ['metricEARProgressText', 'metricMARProgressText', 'metricTiltProgressText', 'metricPerclosProgressText'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '--';
      });
    }
    // Handle alert overlay and device feedback
    const prefs = getAlertPrefs();
    const isDrowsy = s.state === 'DROWSY';

    // Load alert frequency settings
    loadAlertFrequencySettings();

    // Track if alert is currently showing (to prevent auto-hide)
    if (!window.alertCurrentlyShowing) {
      window.alertCurrentlyShowing = false;
    }

    // Check if alert should be shown (considering cooldown and max count)
    let shouldShow = false;
    if (isDrowsy) {
      // If alert is already showing, keep it showing until acknowledged
      if (window.alertCurrentlyShowing) {
        shouldShow = true;
      } else if (shouldShowAlert()) {
        shouldShow = true;
        recordAlertShown();
        window.alertCurrentlyShowing = true; // Mark as showing
      } else {
        // Check why alert is not showing
        const now = Date.now();
        const timeSinceLastAlert = (now - lastAlertTime) / 1000;
        const remainingCooldown = Math.max(0, alertCooldownSeconds - timeSinceLastAlert);

        if (maxAlertCount > 0 && alertCountThisSession >= maxAlertCount) {
          // Max count reached - don't show alert
          console.log(`Alert limit reached: ${alertCountThisSession}/${maxAlertCount} alerts shown`);
        } else if (remainingCooldown > 0) {
          // Still in cooldown - don't show alert
          console.log(`Alert cooldown active: ${Math.ceil(remainingCooldown)}s remaining`);
        }
      }
    } else {
      // Not drowsy anymore - reset alert state to allow new alerts when drowsiness is detected again
      if (window.alertCurrentlyShowing) {
        // State changed from DROWSY to ALERT - reset so new alerts can be shown
        window.alertCurrentlyShowing = false;
        // Reset cooldown timer so new alerts can be shown immediately if drowsiness is detected again
        lastAlertTime = 0;
      }
      shouldShow = false;
    }

    // Show/hide alert overlay
    if (alertOverlay) {
      alertOverlay.classList.toggle('hidden', !shouldShow);

      const alertStatusInfo = document.getElementById('alertStatusInfo');

      // Update alert reason text
      if (shouldShow && alertReason) {
        alertReason.textContent = 'Reason: ' + (s.reason || 'drowsiness');

        // Show alert count info
        if (alertStatusInfo) {
          if (maxAlertCount > 0) {
            alertStatusInfo.textContent = `Alert ${alertCountThisSession} of ${maxAlertCount}`;
          } else {
            alertStatusInfo.textContent = `Alert #${alertCountThisSession}`;
          }
        }
      } else if (isDrowsy && !shouldShow) {
        // Drowsy but alert not shown - show why
        const now = Date.now();
        const timeSinceLastAlert = (now - lastAlertTime) / 1000;
        const remainingCooldown = Math.max(0, alertCooldownSeconds - timeSinceLastAlert);

        if (maxAlertCount > 0 && alertCountThisSession >= maxAlertCount) {
          if (alertReason) {
            alertReason.textContent = `Alert limit reached (${alertCountThisSession}/${maxAlertCount})`;
          }
          if (alertStatusInfo) {
            alertStatusInfo.textContent = 'Please acknowledge previous alerts to continue monitoring.';
          }
        } else if (remainingCooldown > 0) {
          if (alertStatusInfo) {
            alertStatusInfo.textContent = `Cooldown active: ${Math.ceil(remainingCooldown)}s remaining`;
          }
        }
      } else if (alertStatusInfo) {
        alertStatusInfo.textContent = '';
      }
    }

    // Play sounds/vibrations only if alert is actually shown
    if (shouldShow) {
      playAlarm(prefs.sound);
      if (prefs.vibrate) vibrate([300, 200, 300, 200, 600]);
      if (prefs.notify) notify('Drowsiness detected. Please take a break.');
    } else if (isDrowsy) {
      // Stop alarm if drowsy but alert not shown (cooldown/max count)
      playAlarm(false);
    }
  }).catch(() => { });
}
setInterval(pollStatus, 1500);
pollStatus();

const eventsTableBody = document.getElementById('eventsTableBody');
let adminAlertsList = null;
let adminAlertsBadge = null;
let recentAdminAlerts = [];

// Initialize admin alerts elements when DOM is ready
function initAdminAlertsElements() {
  if (!adminAlertsList) {
    adminAlertsList = document.getElementById('adminAlertsList');
  }
  if (!adminAlertsBadge) {
    adminAlertsBadge = document.getElementById('adminAlertsBadge');
  }
  return adminAlertsList !== null;
}
function loadEvents() {
  if (!eventsTableBody) return;
  fetch('/events').then(r => r.json()).then(events => {
    if (!Array.isArray(events)) return;
    if (events.length === 0) {
      eventsTableBody.innerHTML = '<tr class="border-t border-gray-100"><td class="py-2 pr-4" colspan="5" class="text-center text-gray-400">No events yet</td></tr>';
      return;
    }
    eventsTableBody.innerHTML = '';
    for (const e of events.slice(-50).reverse()) {
      const tr = document.createElement('tr');
      tr.className = 'border-t border-gray-100 hover:bg-gray-50';
      const t = new Date(e.time || '').toLocaleString('en-US', { hour12: false }) || '--/--/-- --:--:--';
      const conf = (typeof e.confidence === 'number') ? Math.round(e.confidence * 100) + '%' : '--%';
      let locCell = '<span class="text-gray-400">(no location)</span>';
      try {
        const loc = e.location;
        if (loc && typeof loc.lat === 'number' && typeof loc.lon === 'number') {
          const lat = Number(loc.lat).toFixed(6);
          const lon = Number(loc.lon).toFixed(6);
          const href = `https://maps.google.com/?q=${loc.lat},${loc.lon}`;
          locCell = `<a class="text-blue-600 hover:underline" href="${href}" target="_blank" title="Click to view on Google Maps">${lat}, ${lon}</a>`;
        } else if (loc && (loc.lat || loc.lon)) {
          // Handle string coordinates
          const lat = loc.lat ? Number(loc.lat).toFixed(6) : 'N/A';
          const lon = loc.lon ? Number(loc.lon).toFixed(6) : 'N/A';
          if (lat !== 'N/A' && lon !== 'N/A') {
            const href = `https://maps.google.com/?q=${loc.lat},${loc.lon}`;
            locCell = `<a class="text-blue-600 hover:underline" href="${href}" target="_blank" title="Click to view on Google Maps">${lat}, ${lon}</a>`;
          }
        }
      } catch (err) { 
        console.error('Error parsing location:', err);
      }
      // Enhanced notes display - show reason and type details
      let notesCell = e.notes || '';
      if (e.type && e.type.toLowerCase() === 'drowsiness' && !notesCell) {
        notesCell = 'Drowsiness detected';
      }
      if (e.reason && !notesCell.includes(e.reason)) {
        notesCell = notesCell ? `${notesCell} (${e.reason})` : e.reason;
      }
      tr.innerHTML = `<td class="py-2 pr-4">${t}</td><td class="py-2 pr-4 font-semibold ${e.type === 'Drowsiness' ? 'text-red-600' : 'text-orange-600'}">${e.type || 'Alert'}</td><td class="py-2 pr-4">${conf}</td><td class="py-2 pr-4">${locCell}</td><td class="py-2 pr-4">${notesCell}</td>`;
      eventsTableBody.appendChild(tr);
    }
  }).catch((err) => { 
    console.error('Error loading events:', err);
    if (eventsTableBody) {
      eventsTableBody.innerHTML = '<tr class="border-t border-gray-100"><td class="py-2 pr-4" colspan="5" class="text-center text-red-400">Error loading events</td></tr>';
    }
  });
}
if (eventsTableBody) {
  loadEvents();
  setInterval(loadEvents, 3000);
}

// Admin alerts feed: show recent drowsy events with time and location
async function refreshAdminAlerts(showLoading = false) {
  const role = (localStorage.getItem('role') || 'user').toLowerCase();

  // Ensure elements are initialized
  if (!initAdminAlertsElements()) {
    // Elements don't exist yet, try again later
    setTimeout(() => refreshAdminAlerts(showLoading), 500);
    return;
  }

  // Only run for admin users
  if (role !== 'admin') {
    return;
  }

  if (!adminAlertsList) {
    console.warn('adminAlertsList element not found');
    return;
  }

  const loadingIndicator = document.getElementById('alertsLoadingIndicator');
  if (showLoading && loadingIndicator) {
    loadingIndicator.classList.remove('hidden');
  }

  try {
    let res;
    try {
      // Create timeout promise
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error('TIMEOUT')), 10000); // 10 second timeout
      });

      // Race between fetch and timeout
      res = await Promise.race([
        fetch('/events', {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json'
          }
        }),
        timeoutPromise
      ]);
    } catch (fetchError) {
      // Handle network errors (server down, CORS, timeout, etc.)
      if (fetchError.message === 'TIMEOUT') {
        throw new Error('Request timed out. The server may be slow or unresponsive.');
      } else if (fetchError.name === 'TypeError' && (fetchError.message.includes('fetch') || fetchError.message.includes('Failed'))) {
        throw new Error('Cannot connect to server. Please ensure the Flask backend is running (python app.py).');
      } else {
        throw new Error(`Network error: ${fetchError.message}`);
      }
    }

    if (!res.ok) {
      // Handle different error statuses
      if (res.status === 502) {
        throw new Error('Server is not responding (502 Bad Gateway). Please check if the backend is running.');
      } else if (res.status === 404) {
        throw new Error('Events endpoint not found (404).');
      } else if (res.status === 500) {
        throw new Error('Server error (500). Please check server logs.');
      } else {
        throw new Error(`Server error: ${res.status} ${res.statusText}`);
      }
    }

    const events = await res.json();
    if (!Array.isArray(events)) {
      if (loadingIndicator) loadingIndicator.classList.add('hidden');
      return;
    }

    // Filter and sort drowsy events (most recent first)
    const drowsy = events
      .filter(e => (e.type || '').toLowerCase() === 'drowsiness')
      .slice(-20) // Get last 20 for better history
      .reverse(); // Most recent first

    recentAdminAlerts = drowsy;
    adminAlertsList.innerHTML = '';

    if (loadingIndicator) loadingIndicator.classList.add('hidden');

    if (drowsy.length === 0) {
      adminAlertsList.innerHTML = '<li class="text-gray-400 text-center py-4">No drowsy alerts yet</li>';
    } else {
      // Show only last 10 in the list, but keep all in memory
      const displayAlerts = drowsy.slice(0, 10);

      for (const e of displayAlerts) {
        const li = document.createElement('li');
        li.className = 'border-b border-gray-100 pb-2 last:border-0 hover:bg-gray-50 rounded px-2 py-1.5 transition-colors cursor-pointer';

        const eventTime = e.time ? new Date(e.time) : null;
        const t = eventTime ? eventTime.toLocaleString('en-US', {
          hour12: false,
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        }) : '--/--/-- --:--:--';

        // Calculate time ago
        let timeAgo = '';
        if (eventTime) {
          const now = new Date();
          const diffMs = now - eventTime;
          const diffMins = Math.floor(diffMs / 60000);
          const diffHours = Math.floor(diffMs / 3600000);
          const diffDays = Math.floor(diffMs / 86400000);

          if (diffMins < 1) {
            timeAgo = 'Just now';
          } else if (diffMins < 60) {
            timeAgo = `${diffMins}m ago`;
          } else if (diffHours < 24) {
            timeAgo = `${diffHours}h ago`;
          } else {
            timeAgo = `${diffDays}d ago`;
          }
        }

        let locStr = '<span class="text-gray-400 text-xs">(no location)</span>';
        if (e.location && typeof e.location.lat === 'number' && typeof e.location.lon === 'number') {
          const lat = Number(e.location.lat).toFixed(6);
          const lon = Number(e.location.lon).toFixed(6);
          const href = `https://maps.google.com/?q=${e.location.lat},${e.location.lon}`;
          locStr = `<a class="text-blue-600 hover:underline text-xs" href="${href}" target="_blank" onclick="event.stopPropagation()">${lat}, ${lon}</a>`;
        }

        const conf = (typeof e.confidence === 'number') ? Math.round(e.confidence * 100) + '%' : '--%';
        const notes = e.notes || 'Drowsiness detected';

        li.innerHTML = `
          <div class="flex items-start justify-between gap-3">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="font-semibold text-red-600 text-sm">⚠️ Drowsiness</span>
                <span class="text-xs px-1.5 py-0.5 rounded bg-red-50 text-red-700 font-medium">${conf}</span>
              </div>
              <div class="text-xs text-gray-600 mb-1">${notes}</div>
              <div class="flex items-center gap-3 text-xs text-gray-500">
                <span><i class="ph ph-clock mr-1"></i>${t}</span>
                ${timeAgo ? `<span class="text-gray-400">• ${timeAgo}</span>` : ''}
              </div>
              <div class="mt-1 text-xs">📍 ${locStr}</div>
            </div>
            <button class="text-gray-400 hover:text-gray-600 transition-colors" 
              onclick="event.stopPropagation(); viewAlertDetails('${e.time || ''}')" 
              title="View details">
              <i class="ph ph-arrow-right"></i>
            </button>
          </div>
        `;

        // Add click handler to view driver if possible
        li.addEventListener('click', () => {
          // Try to find driver from location or event data
          if (e.location) {
            // Could scroll to driver monitoring section
            const driverMonitoringSection = document.getElementById('remoteDriverMonitoring');
            if (driverMonitoringSection) {
              driverMonitoringSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
          }
        });

        adminAlertsList.appendChild(li);
      }

      // Show count if more than displayed
      if (drowsy.length > 10) {
        const moreLi = document.createElement('li');
        moreLi.className = 'text-center text-xs text-gray-400 pt-2 border-t border-gray-100';
        moreLi.textContent = `+${drowsy.length - 10} more alerts`;
        adminAlertsList.appendChild(moreLi);
      }
    }

    // Update badge with count
    if (adminAlertsBadge) {
      adminAlertsBadge.textContent = String(drowsy.length);
      // Add animation if new alerts
      if (drowsy.length > 0) {
        adminAlertsBadge.classList.add('animate-pulse');
        setTimeout(() => adminAlertsBadge.classList.remove('animate-pulse'), 1000);
      }
    }
  } catch (e) {
    console.error('Error refreshing admin alerts:', e);
    if (loadingIndicator) loadingIndicator.classList.add('hidden');
    if (adminAlertsList) {
      const errorMsg = e.message || 'Error loading alerts';
      adminAlertsList.innerHTML = `
        <li class="text-red-500 text-center py-4">
          <div class="flex flex-col items-center gap-2">
            <i class="ph ph-warning-circle text-2xl"></i>
            <div class="text-sm font-medium">${errorMsg}</div>
            <div class="text-xs text-gray-500">Please ensure the backend server is running</div>
            <button onclick="refreshAdminAlerts(true)" class="mt-2 px-3 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600">
              Retry
            </button>
          </div>
        </li>
      `;
    }
    // Update badge to show error
    if (adminAlertsBadge) {
      adminAlertsBadge.textContent = '!';
      adminAlertsBadge.classList.add('bg-red-500', 'text-white');
      adminAlertsBadge.title = errorMsg;
    }
  }
}

// View alert details function
function viewAlertDetails(eventTime) {
  // Find the alert in recentAdminAlerts
  const alert = recentAdminAlerts.find(a => a.time === eventTime);
  if (!alert) return;

  // Create a simple modal or alert with details
  const details = [
    `Time: ${new Date(alert.time || '').toLocaleString('en-US', { hour12: false })}`,
    `Confidence: ${typeof alert.confidence === 'number' ? Math.round(alert.confidence * 100) + '%' : '--%'}`,
    `Type: ${alert.type || 'Drowsiness'}`,
    `Notes: ${alert.notes || 'No additional notes'}`,
    alert.location ? `Location: ${alert.location.lat}, ${alert.location.lon}` : 'Location: Not available'
  ].join('\n');

  alert(details);
}

// Initialize admin alerts functionality when DOM is ready
function initAdminAlerts() {
  // Initialize elements
  if (!initAdminAlertsElements()) {
    // Try again after a short delay if elements aren't ready
    setTimeout(initAdminAlerts, 100);
    return;
  }

  // Refresh button handler
  const refreshAlertsBtn = document.getElementById('refreshAlertsBtn');
  if (refreshAlertsBtn) {
    // Remove existing listener if any
    refreshAlertsBtn.onclick = null;
    refreshAlertsBtn.addEventListener('click', () => {
      refreshAdminAlerts(true); // Show loading indicator
    });
  }

  // Initial load
  refreshAdminAlerts(false);
}

// Set up auto-refresh interval (only once)
let adminAlertsInterval = null;
function startAdminAlertsAutoRefresh() {
  if (adminAlertsInterval) return; // Already started

  adminAlertsInterval = setInterval(() => {
    const role = (localStorage.getItem('role') || 'user').toLowerCase();
    if (role === 'admin' && initAdminAlertsElements()) {
      refreshAdminAlerts(false);
    }
  }, 4000);
}

// Initialize when DOM is ready
function setupAdminAlerts() {
  const role = (localStorage.getItem('role') || 'user').toLowerCase();
  if (role === 'admin') {
    initAdminAlerts();
    startAdminAlertsAutoRefresh();
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', setupAdminAlerts);
} else {
  // DOM is already ready
  setupAdminAlerts();
}

// Expose function globally for manual testing (can be called from console)
window.testAdminAlerts = function () {
  console.log('Testing admin alerts...');
  console.log('Role:', localStorage.getItem('role'));
  console.log('adminAlertsList:', document.getElementById('adminAlertsList'));
  console.log('adminAlertsBadge:', document.getElementById('adminAlertsBadge'));
  refreshAdminAlerts(true);
};

// Alert overlay actions
ackAlertBtn?.addEventListener('click', () => {
  fetch('/ack', { method: 'POST' }).finally(() => {
    if (alertOverlay) alertOverlay.classList.add('hidden');
    playAlarm(false);
    // Mark alert as acknowledged so it can be hidden
    window.alertCurrentlyShowing = false;
    // Reset cooldown timer so new alerts can be shown if drowsiness is detected again
    // This allows continuous monitoring - if user becomes drowsy again, alert will show
    lastAlertTime = 0;
    // Note: We don't reset alertCountThisSession here - it should persist until monitoring stops
  });
});


// Settings: alert preferences persistence and backend sync of framesBelow
function getAlertPrefs() {
  try {
    return JSON.parse(localStorage.getItem('alertPrefs') || '{}');
  } catch (e) { return {}; }
}
function saveAlertPrefs(p) {
  localStorage.setItem('alertPrefs', JSON.stringify(p));
}

// Alert frequency control: cooldown timer and max count
let lastAlertTime = 0;
let alertCountThisSession = 0;
let alertCooldownSeconds = 30; // Default 30 seconds
let maxAlertCount = 5; // Default max 5 alerts per session

// Load alert frequency settings
function loadAlertFrequencySettings() {
  const prefs = getAlertPrefs();
  alertCooldownSeconds = prefs.alertCooldown || 30;
  maxAlertCount = prefs.maxAlertCount || 5;

  // Reset count if monitoring just started
  if (!isMonitoringRunning) {
    alertCountThisSession = 0;
  }
}

// Check if alert should be shown based on cooldown and max count
function shouldShowAlert() {
  // If lastAlertTime is 0, no cooldown (allows immediate alerts)
  if (lastAlertTime === 0) {
    // Only check max count
    if (maxAlertCount > 0 && alertCountThisSession >= maxAlertCount) {
      return false; // Max count reached
    }
    return true; // Can show alert immediately
  }

  const now = Date.now();
  const timeSinceLastAlert = (now - lastAlertTime) / 1000; // Convert to seconds

  // Check cooldown (reduced to 5 seconds max for better responsiveness)
  const effectiveCooldown = Math.min(alertCooldownSeconds, 5); // Cap at 5 seconds max
  if (timeSinceLastAlert < effectiveCooldown) {
    return false; // Still in cooldown period
  }

  // Check max count (0 means unlimited)
  if (maxAlertCount > 0 && alertCountThisSession >= maxAlertCount) {
    return false; // Max count reached
  }

  return true; // Can show alert
}

// Record that an alert was shown
function recordAlertShown() {
  lastAlertTime = Date.now();
  alertCountThisSession++;

  // Save to preferences
  const prefs = getAlertPrefs();
  prefs.lastAlertTime = lastAlertTime;
  prefs.alertCountThisSession = alertCountThisSession;
  saveAlertPrefs(prefs);
}

// Reset alert count (called when monitoring starts)
function resetAlertCount() {
  alertCountThisSession = 0;
  const prefs = getAlertPrefs();
  prefs.alertCountThisSession = 0;
  saveAlertPrefs(prefs);
}

const prefAlarmSound = document.getElementById('prefAlarmSound');
const prefVibrate = document.getElementById('prefVibrate');
const prefNotify = document.getElementById('prefNotify');
const framesBelowInput = document.getElementById('framesBelowInput');
const saveAlertPrefsBtn = document.getElementById('saveAlertPrefs');
function initAlertPrefsUI() {
  const p = Object.assign({ sound: true, vibrate: false, notify: false }, getAlertPrefs());
  if (prefAlarmSound) prefAlarmSound.checked = !!p.sound;
  if (prefVibrate) prefVibrate.checked = !!p.vibrate;
  if (prefNotify) prefNotify.checked = !!p.notify;

  // Load alert frequency settings
  loadAlertFrequencySettings();

  // Restore alert count from previous session if monitoring is running
  if (isMonitoringRunning && p.alertCountThisSession) {
    alertCountThisSession = p.alertCountThisSession || 0;
  }
}
initAlertPrefsUI();
saveAlertPrefsBtn?.addEventListener('click', () => {
  const p = {
    sound: !!(prefAlarmSound && prefAlarmSound.checked),
    vibrate: !!(prefVibrate && prefVibrate.checked),
    notify: !!(prefNotify && prefNotify.checked),
  };
  saveAlertPrefs(p);
  const framesBelow = framesBelowInput ? parseInt(framesBelowInput.value || '12', 10) : 12;
  fetch('/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ framesBelow })
  }).catch(() => { });

  // Reload alert frequency settings after saving
  loadAlertFrequencySettings();
});

// IoT settings
const iotEnabledEl = document.getElementById('iotEnabled');
const serialPortSelect = document.getElementById('serialPortSelect');
const refreshPortsBtn = document.getElementById('refreshPortsBtn');
const saveIotBtn = document.getElementById('saveIotBtn');

function loadIotPrefsUI() {
  try {
    const p = JSON.parse(localStorage.getItem('iotPrefs') || '{}');
    if (iotEnabledEl) iotEnabledEl.checked = !!p.enabled;
    if (serialPortSelect && p.port) serialPortSelect.value = p.port;
  } catch (e) { }
}
function saveIotPrefs(p) {
  localStorage.setItem('iotPrefs', JSON.stringify(p));
}
async function refreshPorts() {
  if (!serialPortSelect) return;
  serialPortSelect.innerHTML = '<option>Loading...</option>';
  try {
    const res = await fetch('/serial_ports');
    if (!res.ok) throw new Error('Failed to fetch ports');
    const ports = await res.json();
    serialPortSelect.innerHTML = '';
    
    if (ports.length === 0) {
      serialPortSelect.innerHTML = '<option value="">No Arduino ports found</option>';
    } else {
      ports.forEach(pt => {
        const opt = document.createElement('option');
        opt.value = pt.device;
        opt.textContent = `${pt.device} — ${pt.description || ''}`;
        serialPortSelect.appendChild(opt);
      });
    }
    
    // After refreshing ports, restore the saved port selection
    loadIotPrefsUI();
  } catch (e) {
    // Fail gracefully - Arduino is optional
    serialPortSelect.innerHTML = '<option value="">No ports available (Arduino optional)</option>';
    // Still try to load saved prefs even if refresh failed
    loadIotPrefsUI();
    console.log('Serial ports unavailable (Arduino is optional):', e);
  }
}
refreshPortsBtn?.addEventListener('click', refreshPorts);
saveIotBtn?.addEventListener('click', () => {
  const enabled = !!(iotEnabledEl && iotEnabledEl.checked);
  const port = serialPortSelect ? serialPortSelect.value : '';
  saveIotPrefs({ enabled, port });
  
  // Disable button during save to prevent double-clicks
  const btn = saveIotBtn;
  if (btn) {
    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = 'Saving...';
  }
  
  // Include user email in request for per-user Arduino support
  const email = localStorage.getItem('email') || '';
  const token = localStorage.getItem('token') || '';
  fetch('/settings', {
    method: 'POST', 
    headers: { 
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + token
    },
    body: JSON.stringify({ iotEnabled: enabled, serialPort: port, user_email: email })
  }).then((res) => {
    // Show success feedback
    if (btn) {
      btn.textContent = 'Saved!';
      btn.classList.add('bg-green-600');
      setTimeout(() => {
        btn.textContent = originalText;
        btn.classList.remove('bg-green-600');
        btn.disabled = false;
      }, 2000);
    }
    
    // Show warning if Arduino is enabled but might not be connected
    if (enabled && port) {
      console.log('Arduino enabled. If Arduino is not connected, detection will continue without alerts.');
    }
  }).catch((err) => {
    // Show error but don't break - settings still saved locally
    if (btn) {
      btn.textContent = 'Error';
      btn.classList.add('bg-red-600');
      setTimeout(() => {
        btn.textContent = originalText;
        btn.classList.remove('bg-red-600');
        btn.disabled = false;
      }, 2000);
    }
    console.warn('Settings save error (non-critical):', err);
  });
});
// Load saved preferences first (for enabled checkbox)
loadIotPrefsUI();
// Then refresh ports and restore saved port selection
refreshPorts();

// Camera settings UI
const camWidth = document.getElementById('camWidth');
const camHeight = document.getElementById('camHeight');
const camFps = document.getElementById('camFps');
const camMirror = document.getElementById('camMirror');
const jpegQuality = document.getElementById('jpegQuality');
const saveCamSettings = document.getElementById('saveCamSettings');
const serverCameraSelect = document.getElementById('serverCameraSelect');

async function initCamSettings() {
  if (!saveCamSettings) return;
  try {
    const res = await fetch('/camera_settings');
    const s = await res.json();
    // Load server camera list
    if (serverCameraSelect) {
      try {
        const res2 = await fetch('/camera_devices');
        const devs = await res2.json();
        serverCameraSelect.innerHTML = '';
        devs.forEach(d => {
          const opt = document.createElement('option');
          opt.value = String(d.index);
          opt.textContent = d.label || `Camera ${d.index}`;
          if (typeof s.captureIndex === 'number' && s.captureIndex === d.index) opt.selected = true;
          serverCameraSelect.appendChild(opt);
        });
      } catch (e) {
        serverCameraSelect.innerHTML = '<option value="0">Camera 0</option>';
      }
    }
    if (camWidth && s.width) camWidth.value = s.width;
    if (camHeight && s.height) camHeight.value = s.height;
    if (camFps && s.fps) camFps.value = s.fps;
    if (camMirror) camMirror.checked = !!s.mirror;
    if (jpegQuality && s.jpegQuality) jpegQuality.value = s.jpegQuality;
  } catch (e) { }
}
async function saveCamSettingsFn() {
  const payload = {
    width: camWidth ? parseInt(camWidth.value || '640', 10) : 640,
    height: camHeight ? parseInt(camHeight.value || '480', 10) : 480,
    fps: camFps ? parseInt(camFps.value || '15', 10) : 15,
    mirror: camMirror ? !!camMirror.checked : false,
    jpegQuality: jpegQuality ? parseInt(jpegQuality.value || '80', 10) : 80,
    captureIndex: serverCameraSelect ? parseInt(serverCameraSelect.value || '0', 10) : undefined,
  };
  try {
    const res = await fetch('/camera_settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error('Failed');
    alert('Camera settings applied. If video is running, Stop and Start to reinitialize capture.');
  } catch (e) {
    alert('Failed to apply camera settings');
  }
}
saveCamSettings?.addEventListener('click', saveCamSettingsFn);
initCamSettings();

// Contacts UI
const contactsTableBody = document.getElementById('contactsTableBody');
const contactModal = document.getElementById('contactModal');
const contactModalTitle = document.getElementById('contactModalTitle');
const contactName = document.getElementById('contactName');
const contactPhone = document.getElementById('contactPhone');
const contactNotify = document.getElementById('contactNotify');
const contactCancel = document.getElementById('contactCancel');
const contactSave = document.getElementById('contactSave');
let editingContactId = null;

function renderContacts(contacts) {
  if (!contactsTableBody) return;
  contactsTableBody.innerHTML = '';
  contacts.forEach(c => {
    const tr = document.createElement('tr');
    tr.className = 'border-t border-gray-100';
    tr.innerHTML = `
      <td class="py-2 pr-4">${c.name || ''}</td>
      <td class="py-2 pr-4">${c.phone || ''}</td>
      <td class="py-2 pr-4"><input type="checkbox" ${c.notify ? 'checked' : ''} data-action="toggle" data-id="${c.id}"></td>
      <td class="py-2 pr-4 text-right">
        <button data-action="edit" data-id="${c.id}" class="px-2 py-1 text-xs bg-gray-200 rounded">Edit</button>
        <button data-action="delete" data-id="${c.id}" class="ml-2 px-2 py-1 text-xs bg-red-600 text-white rounded">Delete</button>
      </td>`;
    contactsTableBody.appendChild(tr);
  });
}

async function loadContacts() {
  if (!contactsTableBody) return;
  try {
    const res = await fetch('/contacts');
    const data = await res.json();
    if (Array.isArray(data)) renderContacts(data);
  } catch (e) { }
}

function openContactModal(contact) {
  editingContactId = contact ? contact.id : null;
  if (contactModalTitle) contactModalTitle.textContent = editingContactId ? 'Edit Contact' : 'Add Contact';
  if (contactName) contactName.value = contact ? (contact.name || '') : '';
  if (contactPhone) contactPhone.value = contact ? (contact.phone || '') : '';
  if (contactNotify) contactNotify.checked = !!(contact && contact.notify);
  if (contactModal) contactModal.classList.remove('hidden');
}
function closeContactModal() {
  if (contactModal) contactModal.classList.add('hidden');
}

document.getElementById('addContactBtn')?.addEventListener('click', () => openContactModal(null));
contactCancel?.addEventListener('click', closeContactModal);
contactSave?.addEventListener('click', async () => {
  const payload = {
    name: contactName ? contactName.value.trim() : '',
    phone: contactPhone ? contactPhone.value.trim() : '',
    notify: contactNotify ? !!contactNotify.checked : false,
  };
  if (!payload.name || !payload.phone) { alert('Enter name and phone'); return; }
  try {
    let res;
    if (editingContactId) {
      res = await fetch(`/contacts/${editingContactId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    } else {
      res = await fetch('/contacts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    }
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error('Failed');
    closeContactModal();
    loadContacts();
  } catch (e) {
    alert('Failed to save contact');
  }
});

contactsTableBody?.addEventListener('click', async (e) => {
  const t = e.target;
  if (!(t instanceof HTMLElement)) return;
  const action = t.getAttribute('data-action');
  const id = t.getAttribute('data-id');
  if (action === 'edit' && id) {
    // fetch current to populate
    try {
      const res = await fetch('/contacts');
      const all = await res.json();
      const c = Array.isArray(all) ? all.find(x => x.id === id) : null;
      if (c) openContactModal(c);
    } catch (e) { }
  } else if (action === 'delete' && id) {
    if (!confirm('Delete this contact?')) return;
    try {
      const res = await fetch(`/contacts/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error('Failed');
      loadContacts();
    } catch (e) { alert('Failed to delete'); }
  }
});

contactsTableBody?.addEventListener('change', async (e) => {
  const t = e.target;
  if (!(t instanceof HTMLInputElement)) return;
  if (t.getAttribute('data-action') === 'toggle') {
    const id = t.getAttribute('data-id');
    try {
      await fetch(`/contacts/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ notify: !!t.checked }) });
    } catch (e) { /* noop */ }
  }
});

loadContacts();

async function startBrowserCam() {
  if (!browserCam) return;
  try {
    browserCamStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
    browserCam.srcObject = browserCamStream;
    browserCam.classList.remove('hidden');
    const img = document.getElementById('videoFeed');
    if (img) img.classList.add('hidden');

    // Start processing frames if monitoring is running
    if (isMonitoringRunning) {
      startBrowserCamProcessing();
    }
  } catch (e) {
    alert('Unable to access browser camera');
  }
}

function stopBrowserCam() {
  stopBrowserCamProcessing();

  if (browserCamStream) {
    browserCamStream.getTracks().forEach(t => t.stop());
    browserCamStream = null;
  }
  if (browserCam) browserCam.classList.add('hidden');
  const img = document.getElementById('videoFeed');
  if (img) img.classList.remove('hidden');
}

function startBrowserCamProcessing() {
  if (browserCamProcessingInterval) return;
  if (!browserCam || !browserCamStream) return;

  // Show processing indicator
  const indicator = document.getElementById('browserCamProcessingIndicator');
  if (indicator) indicator.classList.remove('hidden');

  // Create a canvas to capture frames
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  let isProcessing = false; // Prevent overlapping requests

  async function processFrame() {
    // Skip if already processing a frame
    if (isProcessing) {
      return;
    }

    try {
      if (!browserCam || browserCam.classList.contains('hidden')) {
        return;
      }

      isProcessing = true;

      // Reduce resolution for better performance (max 480p)
      const maxWidth = 480;
      const maxHeight = 360;
      const videoWidth = browserCam.videoWidth || 640;
      const videoHeight = browserCam.videoHeight || 480;

      // Calculate scaled dimensions maintaining aspect ratio
      const scale = Math.min(maxWidth / videoWidth, maxHeight / videoHeight);
      canvas.width = videoWidth * scale;
      canvas.height = videoHeight * scale;

      // Draw current video frame to canvas
      ctx.drawImage(browserCam, 0, 0, canvas.width, canvas.height);

      // Convert to base64 with lower quality for better performance
      const frameData = canvas.toDataURL('image/jpeg', 0.6);

      // Send to backend for processing
      const email = localStorage.getItem('email') || '';
      const response = await fetch('/process_frame', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          frame: frameData,
          driver_email: email
        })
      });

      const result = await response.json();

      if (result.ok) {
        // Update UI with detection results (the pollStatus function will pick these up)
        // The backend already updated the monitor's current_status
        // Force immediate status update for better responsiveness
        if (typeof pollStatus === 'function') {
          pollStatus();
        }
      } else {
        console.warn('Frame processing failed:', result.error || 'Unknown error');
      }
    } catch (e) {
      console.error('Frame processing error:', e);
      // Don't stop processing on single error, just log it
    } finally {
      isProcessing = false;
    }
  }

  // Process frames every 200ms (~5 FPS) for better detection responsiveness
  browserCamProcessingInterval = setInterval(processFrame, 200);
}

function stopBrowserCamProcessing() {
  if (browserCamProcessingInterval) {
    clearInterval(browserCamProcessingInterval);
    browserCamProcessingInterval = null;
  }

  // Hide processing indicator
  const indicator = document.getElementById('browserCamProcessingIndicator');
  if (indicator) indicator.classList.add('hidden');
}
if (toggleBrowserCam) {
  toggleBrowserCam.addEventListener('click', () => {
    if (!browserCam) return;
    const isActive = !browserCam.classList.contains('hidden');
    if (isActive) {
      stopBrowserCam();
      toggleBrowserCam.textContent = 'Use Browser Cam';

      // If monitoring is running, switch to server camera
      if (isMonitoringRunning) {
        const video = document.getElementById('videoFeed');
        if (video) {
          const email = localStorage.getItem('email') || '';
          const feedUrl = email ? `/video_feed/${encodeURIComponent(email)}` : '/video_feed';
          video.src = feedUrl;
          video.classList.remove('hidden');
          const placeholder = document.getElementById('videoPlaceholder');
          if (placeholder) placeholder.classList.add('hidden');
        }
      }
    } else {
      startBrowserCam();
      toggleBrowserCam.textContent = 'Use Server Cam';

      // If monitoring is running, switch to browser camera processing
      if (isMonitoringRunning) {
        const video = document.getElementById('videoFeed');
        if (video) {
          video.removeAttribute('src');
          video.src = '';
        }
      }
    }
  });
}

// --- Geolocation posting for SMS map links ---
function postLocation(lat, lon, accuracy) {
  try {
    fetch('/location', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lon, accuracy })
    }).catch(() => { });
  } catch (e) { }
}
if ('geolocation' in navigator) {
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const { latitude, longitude, accuracy } = pos.coords || {};
      if (typeof latitude === 'number' && typeof longitude === 'number') {
        postLocation(latitude, longitude, accuracy);
      }
    },
    () => { },
    { enableHighAccuracy: true, maximumAge: 60000, timeout: 10000 }
  );
  try {
    navigator.geolocation.watchPosition((pos) => {
      const { latitude, longitude, accuracy } = pos.coords || {};
      if (typeof latitude === 'number' && typeof longitude === 'number') {
        postLocation(latitude, longitude, accuracy);
      }
    });
  } catch (e) { }
}

// --- Admin location polling to populate Driver Location card ---
const driverLocationTime = document.getElementById('driverLocationTime');
const driverLocationCoords = document.getElementById('driverLocationCoords');
const driverLocationLink = document.getElementById('driverLocationLink');
const openMapsBtn = document.getElementById('openMapsBtn');
const sendTestSmsBtn = document.getElementById('sendTestSms');
async function pollLocation() {
  const role = (localStorage.getItem('role') || 'user').toLowerCase();
  if (role !== 'admin') return;
  try {
    const res = await fetch('/location');
    const data = await res.json();
    if (data && typeof data.lat === 'number' && typeof data.lon === 'number') {
      if (driverLocationTime) driverLocationTime.textContent = new Date(data.time || Date.now()).toLocaleString('en-US', { hour12: false });
      if (driverLocationCoords) driverLocationCoords.textContent = `${data.lat.toFixed(6)}, ${data.lon.toFixed(6)}`;
      if (driverLocationLink) driverLocationLink.href = `https://maps.google.com/?q=${data.lat},${data.lon}`;
      if (openMapsBtn) {
        openMapsBtn.href = `https://maps.google.com/?q=${data.lat},${data.lon}`;
        openMapsBtn.classList.remove('hidden');
      }
    }
  } catch (e) { }
}
setInterval(pollLocation, 5000);
pollLocation();

// Test SMS trigger (admin only UI is shown conditionally)
sendTestSmsBtn?.addEventListener('click', async () => {
  try {
    const res = await fetch('/test_sms', { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || 'Failed');
    alert('Test SMS triggered. Check your recipients.');
  } catch (e) {
    alert('Failed to send test SMS');
  }
});
