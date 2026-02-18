# Auto Teeth Inspection System - Technical Documentation

## Overview

The Auto Teeth Inspection System is a Python-based application designed for automated inspection of gear teeth using a motorized rotation system and a high-resolution Dino-Lite camera. The system features automatic hardware detection, continuous health monitoring, and intelligent resource management to ensure reliable, high-speed inspection workflows.

### Key Innovations
- **Auto-Detection**: Automatically finds Dino-Lite camera by name and ESP32 motor by VID/PID
- **Health Monitoring**: Continuous ping/pong protocol with adaptive retry timing
- **Smart Resource Management**: Pauses monitoring during inspection to prevent serial port conflicts
- **Background Uploads**: Non-blocking image uploads with automatic temp file cleanup
- **Status Indicators**: Real-time visual feedback with status lights and button states

## System Architecture

```
┌────────────────────────────────────────────────────────────┐
│                         main.py                            │
│               (GUI Application / Controller)               │
│                                                            │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  Config UI  │  │  Controls UI │  │  Preview UI  │       │
│  │  + QR Scan  │  │              │  │              │       │
│  └─────────────┘  └──────────────┘  └──────────────┘       │
└────────────────────────────────────────────────────────────┘
         │                    │                    │
         ├────────────────────┼────────────────────┼────────────┐
         │                    │                    │            │
    ┌────▼─────┐       ┌─────▼──────┐      ┌─────▼──────┐ ┌──▼────────┐
    │ motion.py│       │runner.py   │      │usbc_camera │ │api_client │
    │          │       │            │      │   .py      │ │   .py     │
    │ Arduino  │       │ Inspection │      │            │ │           │
    │ Control  │       │   Logic    │      │  Camera    │ │  Sample   │
    │          │       │            │      │            │ │  Context  │
    │          │       │ Background │      │            │ │  Observe  │
    │          │       │  Uploads   │      │            │ │  Upload   │
    └────┬─────┘       └─────┬──────┘      └─────┬──────┘ └──┬────────┘
         │                   │                   │           │
    ┌────▼─────┐       ┌─────▼──────┐      ┌─────▼──────┐ ┌──▼────────┐
    │ Arduino  │       │kinematics  │      │  OpenCV /  │ │ M.K.Morse │
    │ via      │       │    .py     │      │  Physical  │ │  Testing  │
    │ Serial   │       │            │      │   Camera   │ │    API    │
    │USB/COM   │       │ Angle Math │      └────────────┘ │  (HTTPS)  │
    └──────────┘       └────────────┘                     └───────────┘
```

## File Descriptions

### **main.py** - GUI Application & Main Controller

**Purpose**: The main entry point and GUI application that orchestrates all system components including API integration.

**Key Components**:
- `InspectionGUI` class: Main application window and controller
  - Modern dark-themed UI with status monitoring
  - QR Scan field with auto-focus for immediate scanning
  - Status lights (scan status, motor status)
  - Control buttons (Lock/Release, Start/Stop)
  - Camera preview display with live feed or captured image flash
  - Button state management based on motor connection and inspection state
  - Motor health monitoring with automatic reconnection
  - API integration for observation creation and image upload

**Key Features**:
- Modern dark-themed UI ("AUTO TOOTH INSPECTION")
- **Motor Health Monitoring**:
  - Continuous ping every 3 seconds when connected
  - Automatic reconnection every 1.5 seconds when disconnected
  - Status light: green (connected), red (disconnected)
  - Lock/Release button disabled when motor disconnected
  - Overlay modal when motor not connected (can retry manually)
  - **Smart Monitoring**: Pauses during inspection to prevent serial port conflicts
- **QR Code Scanning**: Auto-focused field for USB scanner input
  - Parses JSON QR codes to extract sample identifier
  - Fetches sample context from API in background thread
  - Auto-populates teeth count
  - Status light turns green on successful scan
  - Stores test case ID and cut number for observation creation
- **API Integration**:
  - Creates observation on active test case when inspection starts
  - Passes observation ID to runner for image uploads
  - Background uploads with temp file cleanup
  - Handles cases with no active test case (local-only mode)
- Live camera preview at 2560x1920 resolution (~30 FPS when possible)
- During inspection: pauses live preview and flashes each captured image
- Thread-safe operations using `threading.Event` for stop signals
- Automatic button state management (enable/disable based on connection and running states)

**Key Methods**:
- `_on_qr_scanned()`: Handle QR code scan, fetch sample context, extract data
- `_start_motor_retry_loop()`: Start continuous motor health monitoring
  - `tick()`: Internal function that pings motor and schedules next check
  - Adaptive timing: 1.5s when disconnected, 3s when connected
  - **Pauses during inspection** to avoid serial port conflicts
- `_motor_connect_worker()`: Background thread to reconnect motor
- `_toggle_blade_lock()`: Lock/release motor (disabled when disconnected)
- `_start_or_stop()`: Toggle inspection start/stop
- `_update_preview()`: Continuous camera preview update loop
- `_display_captured_image()`: Flash captured images during inspection
- `_run_inspection_loop()`: Background thread that runs the inspection sequence
- `_set_light()`: Update scan status indicator (green/red)
- `_set_motor_light()`: Update motor status indicator (green/red)
- `_update_button_states()`: Enable/disable buttons based on state

**API Instance Variables**:
- `sample_context`: Full sample context from API
- `test_case_id`: Active test case ID (None if no active test)
- `cut_number`: Total cuts from active test case
- `observation_id`: Created observation ID

**Dependencies**:
- `motion.py`: For Arduino motion controller communication
- `usbc_camera.py`: For camera capture and preview
- `runner.py`: For inspection sequence execution with background uploads
- `api_client.py`: For QR scanning, observation creation, image upload
- `tkinter`: GUI framework
- `PIL`, `cv2`, `numpy`: Image processing
- `json`: QR code parsing

---

### **motion.py** - ESP32 Motion Controller Interface

**Purpose**: Provides a Python interface to communicate with an ESP32-based motion controller via serial (USB/COM port) with automatic detection and health monitoring.

**Key Components**:
- `MotionConfig` dataclass: Configuration for serial connection
  - `port`: COM port (auto-detected if None, searches for ESP32 CH340)
  - `baud`: Baud rate (default 115200)
  - `connect_reset_delay_s`: Delay after connection for ESP32 reset (2.0s)
  - `read_timeout_s`: Serial read timeout (0.05s)
  - `write_timeout_s`: Serial write timeout (0.2s)
  - `done_token`: Token ESP32 sends when motion completes ("DONE")

- `MotionController` class: Main controller interface
  - Manages serial connection lifecycle
  - Sends commands to ESP32
  - Waits for motion completion
  - **Health monitoring with ping/pong protocol**
  - **Auto-detection by VID/PID**
  - **Automatic reconnection support**

**ESP32 Protocol**:
```
Commands (sent to ESP32):
  H\n  - Hold/enable motor
  R\n  - Release/disable motor
  Z\n  - Zero current position (set to 0 degrees)
  M<degrees>\n  - Move to absolute angle (e.g., "M45.000000\n")
  P\n  - Ping for health check

Responses (from ESP32):
  DONE\n  - Motion complete
  PONG\n  - Health check response
```

**Key Methods**:
- `connect()`: Open serial port and initialize connection
  - Auto-detects ESP32 if port is None
  - Automatically releases motor after connection
- `close()`: Close serial port
- `reconnect()`: Close then reopen connection (for recovery)
- `find_esp_port()`: Auto-detect ESP32 by VID (0x1A86) and PID (0x55D4)
- `ping(timeout)`: Send ping command and wait for PONG response
  - Default timeout: 0.2 seconds
  - Returns True if PONG received
  - Closes connection and returns False on exception
- `hold()`: Enable motor holding current
- `release()`: Disable motor holding current
- `zero()`: Set current position as zero reference
- `move_abs(deg)`: Move to absolute angle in degrees
- `wait_done(timeout_s, stop_flag)`: Wait for "DONE" response with timeout
- `drain()`: Clear serial input buffer

**Key Features**:
- Non-blocking read with buffered line parsing
- Timeout support for motion completion and health checks
- Stop flag support for user cancellation
- Automatic ESP32 reset handling on connection
- **Auto-detection by USB VID/PID** (CH340: VID=0x1A86, PID=0x55D4)
- **Health monitoring** with 200ms ping timeout
- **Automatic recovery** via reconnect() method
- **Text-based protocol** with newline-terminated messages

---

### **usbc_camera.py** - Dino-Lite Camera Interface

**Purpose**: Provides an interface for Dino-Lite Edge 3.0 camera using OpenCV with Windows DirectShow optimization and automatic detection.

**Key Components**:
- `USBCCamera` class: Camera control and capture
  - Single resolution mode: 2560x1920 for both preview and capture
  - Thread-safe frame access with mutex locks
  - DirectShow backend on Windows for better performance
  - **Auto-detection by camera name using pygrabber**

**Key Features**:
- **Auto-Detection**:
  - Uses pygrabber's FilterGraph to enumerate DirectShow devices
  - Searches for "dino-lite" or "dinolite" in device names (case-insensitive)
  - Prints all detected cameras if Dino-Lite not found
  - Raises RuntimeError if no Dino-Lite detected
  
- **Single Resolution Strategy**: Uses 2560x1920 for both preview and capture
  - Eliminates Windows camera on/off indicator flashing
  - No resolution switching during operation
  - Smooth preview performance
  
- **DirectShow Backend** (Windows):
  - Better camera control and performance on Windows
  - Faster initialization
  - More reliable frame capture

- **Thread Safety**:
  - Mutex lock prevents simultaneous preview and capture access
  - Safe for multi-threaded GUI applications

**Key Methods**:
- `find_external_camera()`: Static method to auto-detect Dino-Lite
  - Returns camera index if found, None otherwise
  - Prints detected camera info and all available devices
- `__init__(device_index)`: Initialize camera (auto-detects if device_index is None)
- `open()`: Initialize camera with DirectShow backend (Windows) or default (Linux)
- `close()`: Release camera resources
- `capture_to(filepath)`: Capture and save image to PNG file
  - Flushes 3 frames to get fresh data
  - 30ms delay between flushes
  - Saves as PNG format
- `read_frame()`: Read single frame for preview (returns BGR numpy array)
- `list_available_cameras(max_index)`: Static method to detect available cameras
  - Tests camera indices 0 through max_index-1
  - Stops after 2 consecutive failures
  - Suppresses OpenCV warnings

**Image Format**:
- Captures: 2560x1920 PNG images
- Preview: Same resolution, scaled to fit GUI window
- Color format: BGR (OpenCV standard)

---
---

### **api_client.py** - API Client for M.K. Morse Testing System

**Purpose**: Provides interface to M.K. Morse testing API for sample context retrieval, observation creation, and image upload.

**Key Components**:
- `ApiConfig` dataclass: API configuration
  - `base_url`: API base URL (default: `https://eng-ubuntu.mkmorse.local/api`)
  
- `ApiClient` class: Main API interface
  - Handles HTTPS connections with self-signed certificates
  - JSON request/response handling
  - Comprehensive request/response logging

**Key Methods**:
- `get_sample_context(identifier)`: Fetch sample context from API
  - Endpoint: `GET /samples/identifier/{identifier}/context`
  - Returns sample data including teeth count, active test case, cut number
  
- `create_observation(test_case_id, cut_number)`: Create observation on test case
  - Endpoint: `POST /test-cases/{test_case_id}/observations`
  - Payload: `observation_type_id=1`, `scope="cut"`, `cut_number`
  - Returns observation ID for image uploads
  
- `upload_attachment(observation_id, file_path, tag)`: Upload image to observation
  - Endpoint: `POST /observations/{observation_id}/upload`
  - Multipart form upload with file and tooth number tag
  - Returns attachment metadata

**Helper Functions**:
- `extract_teeth_from_context(ctx)`: Extract teeth count from sample context
- `extract_test_case_id_from_context(ctx)`: Extract active test case ID (or None)
- `extract_cut_number_from_context(ctx)`: Extract cut number from test case
- `api_config_from_env()`: Load API config from environment variables

**API Logging**:
All API calls log detailed information to console:
- Request URL, headers, payload
- Response status, headers, content
- Parsed JSON responses
- Helpful for debugging API issues

**SSL Configuration**:
- Disables SSL verification for self-signed certificates
- Suppresses urllib3 InsecureRequestWarning
- Uses HTTPS by default

**Environment Variables**:
```powershell
$env:MKMORSE_API_BASE_URL = "https://eng-ubuntu.mkmorse.local/api"  # Optional
```

**Sample Context Response**:
```json
{
  "sample": {
    "design": {
      "attribute_values": {
        "Number of Teeth": 60
      }
    }
  },
  "active_test_case": {
    "id": 8,
    "total_cuts": 1400
  }
}
```

---

### **runner.py** - Inspection Sequence Logic

**Purpose**: Orchestrates the automated inspection sequence - moving the motor, capturing images, and uploading to API.

**Key Components**:
- `RunConfig` dataclass: Inspection configuration
  - `teeth`: Number of teeth on the gear
  - `captures`: Number of images to capture (typically matches teeth)
  - `outdir`: Output directory for images
  - `done_timeout_s`: Timeout for each motor movement (default 15.0s)
  - `make_run_subfolder`: Create timestamped subfolder (default True)
  - `observation_id`: Optional observation ID for API uploads
  - `api_config`: Optional API config for uploads
- `cleanup_temp_files`: Delete temp files after successful upload (default False)
  - Takes motion controller, camera, and callbacks
  - Executes full inspection sequence with non-blocking uploads
  - Returns directory where images were saved

**Inspection Sequence**:
1. Create output directory (with timestamp if `make_run_subfolder=True`)
2. Enable motor hold
3. For each capture (0 to captures-1):
   - Calculate target angle using kinematics
   - Send move command to motor
   - Wait for "DONE" signal (with timeout and stop flag check)
   - Capture image to file with tooth number (1-based)
   - **Start background upload thread** (if observation_id provided)
   - Call `on_image_captured` callback (for GUI preview)
   - Continue to next tooth immediately (non-blocking)
   - Log progress
4. Complete and return output directory
5. Upload threads continue running in background

**Background Upload**:
- Each image upload runs in a separate daemon thread
- Upload failures don't stop inspection
- Upload success/failure logged to console
- Multiple uploads can run simultaneously
- **Temp file cleanup**: Files deleted after successful upload when `cleanup_temp_files=True`
- Inspection runs at full speed regardless of upload time

**Callbacks**:
- `on_event`: Called with log messages (e.g., "Move 0/59: 0.000000 deg", "✓ Uploaded tooth_1 to observation")
- `on_image_captured`: Called with filepath after each capture (for GUI display)

**File Naming Convention**:
```
tooth_<number>_deg_<angle>.png

Examples (tooth numbering starts at 1):
tooth_0001_deg_0.000000.png
tooth_0002_deg_5.000000.png
tooth_0060_deg_295.000000.png
```

**Output Directory Structure**:
```
./captures/
├── run_20260216_143025/
│   ├── tooth_0001_deg_0.000000.png
│   ├── tooth_0002_deg_5.000000.png
│   ├── tooth_0003_deg_10.000000.png
│   └── ...
└── run_20260216_144532/
    └── ...
```

---

### **kinematics.py** - Angle Calculation Utilities

**Purpose**: Provides mathematical functions for calculating rotation angles based on gear teeth count and capture index.

**Key Functions**:

1. `step_angle_deg(teeth: int) -> float`
   - Calculates the angle between adjacent teeth
   - Formula: `360.0 / teeth`
   - Example: 72 teeth → 5.0 degrees per tooth

2. `index_to_angle_deg(index: int, teeth: int) -> float`
   - Converts capture index to absolute rotation angle
   - Formula: `index * (360.0 / teeth)`
   - Example with 72 teeth:
     - Index 0 → 0.0 degrees
     - Index 1 → 5.0 degrees
     - Index 36 → 180.0 degrees
     - Index 71 → 355.0 degrees

**Usage in System**:
```python
# For a gear with 72 teeth, capturing 72 images:
teeth = 72
captures = 72

for i in range(captures):
    angle = index_to_angle_deg(i, teeth)  # 0.0, 5.0, 10.0, ...
    motor.move_abs(angle)
    # ... wait and capture
```

---

## System Workflow

### 1. **Startup**
```
1. User runs main.py
2. GUI window opens (zoomed/maximized)
3. System auto-detects hardware:
   a. Camera: Searches for Dino-Lite by name using pygrabber
      - Prints: "[CAMERA] Detected Dino-Lite at index X: <name>"
      - Raises error if not found
   b. Motor: Searches for ESP32 by VID/PID (0x1A86/0x55D4)
      - Auto-starts connection retry loop
      - Shows motor overlay if not connected
   c. Motor status light: Red (disconnected), Green (connected)
4. Default configuration loaded (teeth count 72)
5. QR Scan field automatically focused for immediate scanning
6. Motor health monitoring starts:
   - Pings every 3 seconds when connected
   - Retries connection every 1.5 seconds when disconnected
```

### 2. **QR Code Scanning (Optional)**
```
1. User positions cursor in QR Scan field (auto-focused)
2. User scans sample QR code with USB scanner
   - QR code format: {"type":"sample","identifier":"TEST_60"}
3. User presses Enter (or scanner auto-enters)
4. System parses JSON to extract identifier
5. Background thread fetches sample context from API:
   - GET /samples/identifier/{identifier}/context
6. System extracts data from context:
   - Teeth count from sample.design.attribute_values["Number of Teeth"]
   - Test case ID from active_test_case.id
   - Cut number from active_test_case.total_cuts
7. GUI updates:
   - Teeth Count field auto-populated
   - Log shows test case ID and cut number
   - Warning shown if no active test case
8. QR Scan field clears for next scan
9. Status: Ready for inspection with API integration
```

### 3. **Connection**
```
1. System automatically attempts motor connection on startup
2. find_esp_port() searches for CH340 USB device (VID: 0x1A86, PID: 0x55D4)
3. Serial connection opened at 115200 baud
4. ESP32 resets (2 second delay)
5. Serial buffer cleared
6. Motor automatically released ("R\n" command)
7. Health monitoring begins (ping every 3s)
8. Motor status light: Green
9. Lock/Release button: Enabled
10. Motor overlay: Hidden
Status: Connected and monitoring
```

### 4. **Motor Setup**
```
1. User clicks "Lock" button
2. System sends "H\n" command (enable motor)
3. System sends "Z\n" command (zero position)
4. Motor is now holding at position 0.0 degrees
5. Button shows "Release"
Status: Motor locked and zeroed
```

### 5. **Camera Preview**
```
1. System auto-detects Dino-Lite camera on startup
   - Uses pygrabber FilterGraph to enumerate DirectShow devices
   - Matches "dino-lite" or "dinolite" in camera name
2. Camera opens with DirectShow backend (Windows)
3. Resolution set to 2560x1920
4. Preview starts automatically at ~30 FPS
5. Images scaled to fit preview area
Status: Live preview running
```

### 6. **Inspection Run**
```
1. User sets configuration (or auto-populated from QR scan):
   - Teeth count: 60  (from QR scan or manual entry)
   - Captures matches teeth count automatically
   
2. User clicks "Start/Stop" button
3. System validates inputs
4. **Motor monitoring pauses** (tick() returns early during inspection)
   - Prevents serial port conflicts between ping and move commands
   - Monitoring resumes after inspection completes
5. If test case ID exists from QR scan:
   a. Create observation on test case via API:
      - POST /test-cases/{test_case_id}/observations
      - Payload: observation_type_id=1, scope="cut", cut_number
   b. Store observation ID for uploads
   c. Log: "✓ Created observation ID: 123"
6. If no test case: Log warning "Running locally without API upload"
7. Live preview pauses
8. Creates temporary directory (if cleanup enabled) or timestamped folder
9. For each of 60 captures (teeth):
   a. Calculate angle: 0°, 6°, 12°, ... 354°
   b. Send move command: "M6.000000\n"
   c. Wait for "DONE" response (max 15s)
      - No ping commands interfere (monitoring paused)
   d. Flush camera buffer (3 frames, 90ms total)
   e. Capture image to PNG (tooth_0001, tooth_0002, ...)
   f. Start background upload thread (non-blocking):
      - POST /observations/{observation_id}/upload
      - Multipart: file + tag (tooth number 1-based)
      - Log: "✓ Uploaded tooth_1 to observation" (async)
      - **Delete temp file after successful upload**
   g. Flash image in preview immediately
   h. Continue to next tooth without waiting for upload
   i. Log progress to console
10. Inspection complete (uploads continue in background)
11. Live preview resumes
12. **Motor monitoring resumes** (health checks restart)
13. Background upload threads finish
14. Temp files deleted (only temp directory remains)
Status: Inspection complete, all images uploaded, temp files cleaned
```

### 7. **Shutdown**
```
1. User clicks close button (X) or presses Alt+F4
2. Live preview stops
3. Camera released
4. Motor monitoring stops
5. Serial connection closed (if open)
6. Application exits cleanly
```

---

## Key Technical Decisions

### 1. **Auto-Detection Instead of Manual Configuration**
- **Decision**: Auto-detect both camera (by name) and motor (by VID/PID)
- **Rationale**:
  - Eliminates user configuration errors
  - Faster workflow (no manual COM port entry)
  - Works across different computers without reconfiguration
  - Prevents connecting to wrong devices
- **Implementation**: pygrabber for camera names, serial.tools.list_ports for USB VID/PID
- **Trade-off**: Requires specific hardware (Dino-Lite Edge 3.0, ESP32 with CH340)

### 2. **Health Monitoring with Ping/Pong Protocol**
- **Decision**: Continuous motor health monitoring with adaptive timing
- **Rationale**:
  - Immediate detection of disconnections
  - Visual feedback with status lights
  - Automatic reconnection without user intervention
  - Prevents starting inspection with disconnected motor
- **Implementation**: 
  - Custom "P\n" command with "PONG\n" response
  - 200ms timeout for health checks
  - 3s interval when connected, 1.5s when disconnected
- **Trade-off**: Additional serial traffic, requires Arduino firmware support

### 3. **Pause Monitoring During Inspection**
- **Decision**: Skip health monitoring while inspection is running
- **Rationale**:
  - Prevents serial port race conditions
  - PONG and DONE responses could collide
  - Inspection thread needs exclusive serial port access
  - Monitoring resumes immediately after completion
- **Implementation**: Check `is_running` flag in tick() function, return early
- **Trade-off**: No health monitoring during inspection (acceptable, inspection is short)

### 4. **Single Resolution for Camera**
- **Decision**: Use 2560x1920 for both preview and capture
- **Rationale**: 
  - Eliminates Windows camera indicator flashing during resolution switching
  - Simpler code with no resolution management complexity
  - Modern hardware can handle high-res preview
- **Trade-off**: Higher CPU usage for preview, but acceptable on modern systems

### 5. **DirectShow Backend on Windows**
- **Decision**: Use `cv2.CAP_DSHOW` on Windows for camera access
- **Rationale**:
  - Better camera control and performance
  - Faster initialization
  - More reliable frame capture
  - Standard Windows camera API
- **Cross-platform**: Falls back to default backend on Linux/Mac

### 6. **Flash Captured Images During Inspection**
- **Decision**: Pause live preview and flash each captured image
- **Rationale**:
  - Prevents camera indicator from flashing on/off
  - Provides visual feedback of capture progress
  - Reduces simultaneous camera access
  - User sees what was actually captured
- **Implementation**: Callback from runner to GUI for image display

### 7. **Thread-Safe Design**
- **Decision**: Use mutex locks for camera access, Event flags for stop signals
- **Rationale**:
  - GUI runs in main thread (Tkinter requirement)
  - Inspection runs in background thread
  - Preview and capture access camera simultaneously
  - Stop button needs to signal background thread
- **Implementation**: `threading.Lock` for camera, `threading.Event` for stop

### 8. **Buffer Flushing Before Capture**
- **Decision**: Read and discard 3 frames before capturing
- **Rationale**:
  - Ensures fresh frame after motor stops
  - Eliminates motion blur from buffered frames
  - OpenCV buffers several frames internally
- **Timing**: 30ms delay between flushes (total ~90ms)

### 9. **Non-Blocking Background Uploads with Temp Cleanup**
- **Decision**: Upload images in separate daemon threads, delete after success
- **Rationale**:
  - Inspection runs at full speed regardless of network conditions
  - No delay between captures waiting for uploads
  - Upload failures don't stop inspection
  - Multiple uploads can run simultaneously
  - Saves disk space (temp files deleted)
  - Only uploads persist in API database
- **Implementation**: Each upload spawns a daemon thread with upload_worker function
- **Trade-off**: Upload completion is asynchronous (check console logs for status)

### 10. **Temp Files vs Permanent Storage**
- **Decision**: Use temp directory with cleanup when API enabled, permanent folders when local-only
- **Rationale**:
  - API is source of truth (images in database)
  - No need to keep local copies after upload
  - Saves disk space on inspection machine
  - Local-only mode still preserves files for backup
- **Implementation**: `cleanup_temp_files` flag in RunConfig

### 11. **QR Code JSON Parsing**
- **Decision**: Parse QR codes as JSON to extract identifier field
- **Rationale**:
  - QR codes contain structured data: {"type":"sample","identifier":"TEST_60"}
  - Supports future QR code formats
  - Falls back to raw string if not valid JSON
  - Explicit field extraction prevents errors
- **Implementation**: Try JSON parse, fallback to raw string on error

### 12. **Tooth Numbering Starts at 1**
- **Decision**: File names and API tags use 1-based numbering (tooth_0001, tooth_0002, ...)
- **Rationale**:
  - More intuitive for users (first tooth is #1, not #0)
  - Matches industry convention
  - Easier visual identification
  - API tags align with user expectations
- **Implementation**: `tooth_num = i + 1` where i is loop index (0-based)

### 13. **Status Lights Instead of Text Labels**
- **Decision**: Use colored circles (green/red) for status indicators
- **Rationale**:
  - Instant visual feedback
  - Color-coded for quick recognition
  - Less UI clutter than text messages
  - Modern, clean interface
- **Implementation**: Canvas with oval shapes, color updates

### 14. **Motor Overlay Modal**
- **Decision**: Show full-screen overlay when motor disconnected
- **Rationale**:
  - Prevents operation without motor
  - Clear visual indication of problem
  - Provides manual retry option
  - Blocks UI interaction until resolved
- **Implementation**: Tkinter frame with place() geometry, manual retry button

---

## Configuration Reference

### Default Values
```python
# Motion Controller
COM_PORT = "COM9"              # Windows: COMx, Linux: /dev/ttyACMx
BAUD_RATE = 115200
CONNECT_DELAY = 2.0            # Arduino reset delay

# Inspection
TEETH_COUNT = 72               # Number of gear teeth (auto-populated from QR)
CAPTURES = TEETH_COUNT         # Matches teeth count automatically
OUTPUT_DIR = "./captures"
DONE_TIMEOUT = 15.0            # Max wait time per movement
MAKE_SUBFOLDER = True          # Create timestamped run folders

# Camera
CAMERA_INDEX = 1               # 0, 1, 2, ... (check dropdown)
RESOLUTION = 2560x1920         # Single resolution for preview and capture

# API Integration
API_BASE_URL = "https://eng-ubuntu.mkmorse.local/api"  # Default
API_TIMEOUT = 10               # Seconds for API requests
API_UPLOAD_TIMEOUT = 30        # Seconds for image uploads
SSL_VERIFY = False             # Disable for self-signed certs

# Preview
PREVIEW_FPS = 30               # Target frame rate
UPDATE_INTERVAL = 33           # ms (33ms ≈ 30 FPS)
```

### File Locations
```
Project Root/
├── main.py                    # GUI application
├── motion.py                  # Motion controller
├── usbc_camera.py             # Camera interface
├── runner.py                  # Inspection logic
├── api_client.py              # API integration with M.K. Morse system
├── kinematics.py              # Angle calculations
├── requirements.txt           # Python dependencies
├── README.md                  # User guide
├── DOCUMENTATION.md           # This file
└── captures/                  # Output directory (created automatically)
    └── run_YYYYMMDD_HHMMSS/   # Timestamped run folders
        └── tooth_0001.png     # Captured images (1-based numbering)
        └── tooth_0002.png
        └── ...
```

---

## Hardware Requirements

### Motion Controller (ESP32)
- ESP32 development board with CH340 USB-to-Serial (VID: 0x1A86, PID: 0x55D4)
- USB connection for serial communication (auto-detected)
- Must implement the command protocol (H, R, Z, M, P commands)
- Must send "DONE\n" after completing movements
- Must send "PONG\n" in response to ping commands
- Recommended: Stepper motor with driver (TMC2209, DRV8825, etc.)

### Camera
- **Dino-Lite Edge 3.0** USB microscope camera (required for auto-detection)
- Resolution: 2560x1920 or higher
- Supported by OpenCV VideoCapture
- Windows: DirectShow compatible
- USB 3.0 recommended for best performance

### Computer
- Windows 10/11 (primary target)
- Python 3.11 or higher
- USB ports for ESP32 and camera
- Recommended: 8GB+ RAM for high-res preview
- Recommended: Modern CPU for real-time preview and background uploads

---

## Error Handling

### Common Errors and Solutions

**1. Camera Warnings on Startup**
```
[ WARN:0@1.782] global cap.cpp:480 cv::VideoCapture::open VIDEOIO(DSHOW): 
backend is generally available but can't be used to capture by index
```
- **Cause**: System testing non-existent camera indices during detection
- **Solution**: Harmless, can be ignored - stops after 2 consecutive failures
- **Prevention**: Already minimized by early termination logic

**2. Serial Connection Failed**
```
Failed to connect: [Errno 13] Permission denied: 'COM9'
```
- **Cause**: COM port already in use or wrong port number
- **Solution**: Close other serial programs, verify port in Device Manager

**3. Motion Timeout**
```
WAIT DONE failed (timeout/stop) at index 5.
```
- **Cause**: Arduino not responding, mechanical issue, or cable disconnected
- **Solution**: Check Arduino power, verify serial connection, increase timeout

**4. Camera Not Opening**
```
Failed to open camera at index 1
```
- **Cause**: Wrong camera index, camera in use by another program
- **Solution**: Try different camera index, close other camera applications

**5. QR Scan - No Active Test Case**
```
[WARNING] No active test case found. Inspection will run locally without creating observation.
```
- **Cause**: QR code sample has no active test case in the API
- **Impact**: Inspection runs normally, images saved locally, but not uploaded to API
- **Solution**: Create test case for sample in M.K. Morse system, or proceed with local-only operation

**6. Observation Creation Failed**
```
[ERROR] Failed to create observation: ...
```
- **Cause**: API unavailable, network error, or invalid test case ID
- **Impact**: Inspection will NOT start (prevents orphaned images)
- **Solution**: Check network connection to API server, verify QR code scanned correctly, try re-scanning

**7. Upload Failed for Individual Tooth**
```
[API] ❌ Upload failed for tooth 5 to observation 123: Connection timeout
```
- **Cause**: Network issue, API server down, or file read error
- **Impact**: Inspection continues (non-blocking), other images still upload
- **Solution**: Check console logs for which teeth failed, retry upload manually if needed

**8. SSL Certificate Verification Error**
```
SSLError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed
```
- **Cause**: Self-signed certificate on API server
- **Solution**: Already handled - verify=False and InsecureRequestWarning suppressed in api_client.py
- **Note**: This is expected behavior with the M.K. Morse API

---

## Development Notes

### Adding New Features

**To add a new motor command**:
1. Add method to `MotionController` class in `motion.py`
2. Update Arduino firmware to handle new command
3. Add UI button/control in `main.py` if needed

**To change capture resolution**:
1. Modify `width` and `height` parameters in `USBCCamera.__init__()` in `usbc_camera.py`
2. Update documentation

**To add new inspection modes**:
1. Create new config dataclass in `runner.py`
2. Add new inspection function in `runner.py`
3. Update GUI to support new mode in `main.py`

### Testing

**Test camera without GUI**:
```python
from usbc_camera import USBCCamera

# List cameras
cameras = USBCCamera.list_available_cameras(max_index=5)
print(f"Available cameras: {cameras}")

# Test camera 1
with USBCCamera(device_index=1) as cam:
    cam.capture_to("test.png")
    print("Test capture saved to test.png")
```

**Test motion controller without GUI**:
```python
from motion import MotionController, MotionConfig

config = MotionConfig(port="COM9")
with MotionController(config) as motion:
    motion.hold()
    motion.zero()
    motion.move_abs(45.0)
    motion.wait_done(timeout_s=10.0)
    print("Moved to 45 degrees")
```

---

## Version History

- **Current Version**: Production v2.0 - Auto-Detection & Health Monitoring
  - **Auto-Detection**: Automatically finds Dino-Lite camera by name and ESP32 motor by VID/PID
  - **Health Monitoring**: Continuous ping/pong protocol with adaptive timing
  - **Smart Resource Management**: Pauses monitoring during inspection to prevent serial port conflicts
  - **Status Indicators**: Real-time visual feedback with colored status lights
  - **Motor Overlay**: Full-screen modal when motor disconnected with manual retry
  - **Temp File Cleanup**: Automatically deletes temp files after successful upload
  - **Button State Management**: Lock/Release button disabled when motor disconnected
  - **pygrabber Integration**: Uses FilterGraph for DirectShow device enumeration
  - **ESP32 Support**: Auto-detects CH340 USB devices (VID: 0x1A86, PID: 0x55D4)
  - **Adaptive Retry Timing**: 1.5s when disconnected, 3s health check when connected
  - **Serial Port Conflict Prevention**: Monitor tick() returns early during inspection
  - **1-Based Tooth Numbering**: Files and API tags use tooth_0001, tooth_0002, etc.
  
- **Previous Version**: Production v1.0 - API Integration
  - **QR Code Integration**: Scan QR codes to fetch sample data from M.K. Morse API
  - **API Integration**: Automatic observation creation and image uploads
  - **Non-Blocking Uploads**: Background threading for uploads (inspection runs at full speed)
  - **Auto-Focus QR Field**: QR scan field focused on startup for immediate scanning
  - **Comprehensive API Logging**: All API requests/responses logged to console for debugging
  - **HTTPS Support**: Default API endpoint uses HTTPS with self-signed certificate support
  - Auto-populated teeth count from API sample design
  - Warnings for missing test cases (local-only mode)

- **Earlier Version**: Windows Branch
  - Single resolution camera (2560x1920)
  - Flash captured images during inspection
  - Fixed preview sizing issues
  - DirectShow backend support
  - Removed GUI logs panel

- **Initial Version**: CV-Camera Branch
  - Dual resolution camera support
  - GUI logs panel
  - Live preview during inspection

---

## Support

For issues or questions:
1. Check error logs in console output
2. Verify hardware connections
3. Test components individually (camera, motion controller)
4. Review this documentation for configuration details

## License

Copyright M.K. Morse Company
