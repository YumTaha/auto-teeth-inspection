# Auto Teeth Inspection System - Technical Documentation

## Overview

The Auto Teeth Inspection System is a Python-based application designed for automated inspection of gear teeth using a motorized rotation system and a high-resolution USB-C camera. The system rotates a gear incrementally, capturing high-quality images at precise angles for quality control and inspection purposes.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                              │
│                  (GUI Application / Controller)               │
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  Config UI  │  │  Controls UI │  │  Preview UI  │       │
│  │  + QR Scan  │  │              │  │              │       │
│  └─────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
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
         │                    │                    │            │
    ┌────▼─────┐       ┌─────▼──────┐      ┌─────▼──────┐ ┌──▼────────┐
    │ Arduino  │       │kinematics  │      │  OpenCV /  │ │ M.K.Morse │
    │ via      │       │    .py     │      │  Physical  │ │  Testing  │
    │ Serial   │       │            │      │   Camera   │ │    API    │
    │USB/COM   │       │ Angle Math │      └────────────┘ │  (HTTPS)  │
    └──────────┘       └────────────┘                      └───────────┘
```

## File Descriptions

### **main.py** - GUI Application & Main Controller

**Purpose**: The main entry point and GUI application that orchestrates all system components including API integration.

**Key Components**:
- `InspectionGUI` class: Main application window and controller
  - Configuration panel (COM port, QR scan, teeth count, output directory, camera index)
  - QR Scan field with auto-focus for immediate scanning
  - Control buttons (Connect, Hold Motor, Release Motor, Start Inspection, Stop, Exit)
  - Camera preview display with live feed or captured image flash
  - Button state management based on system state
  - API integration for observation creation and image upload

**Key Features**:
- Tkinter-based GUI with maximized window
- **QR Code Scanning**: Auto-focused field for USB scanner input
  - Parses JSON QR codes to extract sample identifier
  - Fetches sample context from API in background thread
  - Auto-populates teeth count
  - Stores test case ID and cut number for observation creation
- **API Integration**:
  - Creates observation on active test case when inspection starts
  - Passes observation ID to runner for image uploads
  - Handles cases with no active test case (local-only mode)
- Live camera preview at 2560x1920 resolution (~30 FPS when possible)
- During inspection: pauses live preview and flashes each captured image
- Thread-safe operations using `threading.Event` for stop signals
- Automatic button state management (enable/disable based on connection and running states)

**Key Methods**:
- `_on_qr_scanned()`: Handle QR code scan, fetch sample context, extract data
- `_toggle_connection()`: Connect/disconnect to Arduino motion controller
- `_hold_motor()`: Enable motor and zero position
- `_release_motor()`: Disable motor
- `_start_inspection()`: Create observation, validate inputs, start inspection in background thread
- `_update_preview()`: Continuous camera preview update loop
- `_display_captured_image()`: Flash captured images during inspection
- `_run_inspection_worker()`: Background thread that runs the inspection sequence

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

### **motion.py** - Arduino Motion Controller Interface

**Purpose**: Provides a Python interface to communicate with an Arduino-based motion controller via serial (USB/COM port).

**Key Components**:
- `MotionConfig` dataclass: Configuration for serial connection
  - `port`: COM port (e.g., "COM9" on Windows, "/dev/ttyACM0" on Linux)
  - `baud`: Baud rate (default 115200)
  - `connect_reset_delay_s`: Delay after connection for Arduino reset (2.0s)
  - `read_timeout_s`: Serial read timeout (0.05s)
  - `write_timeout_s`: Serial write timeout (0.2s)
  - `done_token`: Token Arduino sends when motion completes ("DONE")

- `MotionController` class: Main controller interface
  - Manages serial connection lifecycle
  - Sends commands to Arduino
  - Waits for motion completion

**Arduino Protocol**:
```
Commands (sent to Arduino):
  H\n  - Hold/enable motor
  R\n  - Release/disable motor
  Z\n  - Zero current position (set to 0 degrees)
  M<degrees>\n  - Move to absolute angle (e.g., "M45.000000\n")

Responses (from Arduino):
  DONE\n  - Motion complete
```

**Key Methods**:
- `connect()`: Open serial port and initialize connection
- `close()`: Close serial port
- `hold()`: Enable motor holding current
- `release()`: Disable motor holding current
- `zero()`: Set current position as zero reference
- `move_abs(deg)`: Move to absolute angle in degrees
- `wait_done(timeout_s, stop_flag)`: Wait for "DONE" response with timeout
- `drain()`: Clear serial input buffer

**Key Features**:
- Non-blocking read with buffered line parsing
- Timeout support for motion completion
- Stop flag support for user cancellation
- Automatic Arduino reset handling on connection

---

### **usbc_camera.py** - USB-C Camera Interface

**Purpose**: Provides an interface for USB-C/webcam capture using OpenCV with Windows DirectShow optimization.

**Key Components**:
- `USBCCamera` class: Camera control and capture
  - Single resolution mode: 2560x1920 for both preview and capture
  - Thread-safe frame access with mutex locks
  - DirectShow backend on Windows for better performance

**Key Features**:
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

- `run_inspection()` function: Main inspection loop
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
2. GUI window opens (maximized)
3. System detects available cameras (shows DirectShow warnings for non-existent indices)
4. Camera dropdown populated with available cameras
5. Default configuration loaded (COM port, teeth count, etc.)
6. QR Scan field automatically focused for immediate scanning
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
1. User enters COM port (e.g., COM9)
2. User clicks "Connect"
3. System opens serial connection to Arduino
4. Arduino resets (2 second delay)
5. Serial buffer cleared
6. Status: Connected (button changes to "Disconnect")
```

### 4. **Motor Setup**
```
1. User clicks "Hold Motor"
2. System sends "H\n" command (enable motor)
3. System sends "Z\n" command (zero position)
4. Motor is now holding at position 0.0 degrees
5. Status: Motor enabled and zeroed
```

### 5. **Camera Preview**
```
1. User selects camera index from dropdown
2. User clicks "Connect" (if not already connected)
3. Camera opens with DirectShow backend (Windows)
4. Resolution set to 2560x1920
5. Preview starts at ~30 FPS
6. Images scaled to fit preview area
7. Status: Live preview running
```

### 6. **Inspection Run**
```
1. User sets configuration (or auto-populated from QR scan):
   - Teeth count: 60  (from QR scan or manual entry)
   - Output dir: ./captures
   - Captures matches teeth count automatically
   
2. User clicks "Start Inspection"
3. System validates inputs
4. If test case ID exists from QR scan:
   a. Create observation on test case via API:
      - POST /test-cases/{test_case_id}/observations
      - Payload: observation_type_id=1, scope="cut", cut_number
   b. Store observation ID for uploads
   c. Log: "✓ Created observation ID: 123"
5. If no test case: Log warning "Running locally without API upload"
6. Live preview pauses
7. Creates timestamped output folder
8. For each of 60 captures (teeth):
   a. Calculate angle: 0°, 6°, 12°, ... 354°
   b. Send move command: "M6.000000\n"
   c. Wait for "DONE" response (max 15s)
   d. Flush camera buffer (3 frames, 90ms total)
   e. Capture image to PNG (tooth_0001, tooth_0002, ...)
   f. Start background upload thread (non-blocking):
      - POST /observations/{observation_id}/upload
      - Multipart: file + tag (tooth number 1-based)
      - Log: "✓ Uploaded tooth_1 to observation" (async)
   g. Flash image in preview immediately
   h. Continue to next tooth without waiting for upload
   i. Log progress to console
9. Inspection complete (uploads continue in background)
10. Live preview resumes
11. Background upload threads finish
12. Status: Inspection complete, all images uploaded
```

### 7. **Shutdown**
```
1. User clicks "Exit" or closes window
2. Live preview stops
3. Camera released
4. Serial connection closed (if open)
5. Application exits
```

---

## Key Technical Decisions

### 1. **Single Resolution for Camera**
- **Decision**: Use 2560x1920 for both preview and capture
- **Rationale**: 
  - Eliminates Windows camera indicator flashing during resolution switching
  - Simpler code with no resolution management complexity
  - Modern hardware can handle high-res preview
- **Trade-off**: Higher CPU usage for preview, but acceptable on modern systems

### 2. **DirectShow Backend on Windows**
- **Decision**: Use `cv2.CAP_DSHOW` on Windows for camera access
- **Rationale**:
  - Better camera control and performance
  - Faster initialization
  - More reliable frame capture
  - Standard Windows camera API
- **Cross-platform**: Falls back to default backend on Linux/Mac

### 3. **Flash Captured Images During Inspection**
- **Decision**: Pause live preview and flash each captured image
- **Rationale**:
  - Prevents camera indicator from flashing on/off
  - Provides visual feedback of capture progress
  - Reduces simultaneous camera access
  - User sees what was actually captured
- **Implementation**: Callback from runner to GUI for image display

### 4. **Thread-Safe Design**
- **Decision**: Use mutex locks for camera access, Event flags for stop signals
- **Rationale**:
  - GUI runs in main thread (Tkinter requirement)
  - Inspection runs in background thread
  - Preview and capture access camera simultaneously
  - Stop button needs to signal background thread
- **Implementation**: `threading.Lock` for camera, `threading.Event` for stop

### 5. **Buffer Flushing Before Capture**
- **Decision**: Read and discard 3 frames before capturing
- **Rationale**:
  - Ensures fresh frame after motor stops
  - Eliminates motion blur from buffered frames
  - OpenCV buffers several frames internally
- **Timing**: 30ms delay between flushes (total ~90ms)

### 6. **Logs to Console Instead of GUI**
- **Decision**: Remove GUI log panel, print to console
- **Rationale**:
  - More space for camera preview
  - Simpler GUI layout
  - Console logs persist after program exit
  - Easier debugging and log capture
- **Trade-off**: Users must run from terminal to see logs

### 7. **Non-Blocking Background Uploads**
- **Decision**: Upload images in separate daemon threads while inspection continues
- **Rationale**:
  - Inspection runs at full speed regardless of network conditions
  - No delay between captures waiting for uploads
  - Upload failures don't stop inspection
  - Multiple uploads can run simultaneously
- **Implementation**: Each upload spawns a daemon thread with upload_worker function
- **Trade-off**: Upload completion is asynchronous (check console logs for status)

### 8. **QR Code JSON Parsing**
- **Decision**: Parse QR codes as JSON to extract identifier field
- **Rationale**:
  - QR codes contain structured data: {"type":"sample","identifier":"TEST_60"}
  - Supports future QR code formats
  - Falls back to raw string if not valid JSON
  - Explicit field extraction prevents errors
- **Implementation**: Try JSON parse, fallback to raw string on error

### 9. **Tooth Numbering Starts at 1**
- **Decision**: File names and API tags use 1-based numbering (tooth_0001, tooth_0002, ...)
- **Rationale**:
  - More intuitive for users (first tooth is #1, not #0)
  - Matches industry convention
  - Easier visual identification
  - API tags align with user expectations
- **Implementation**: `tooth_num = i + 1` where i is loop index (0-based)

### 10. **Auto-Focus QR Scan Field**
- **Decision**: QR Scan field receives focus automatically on startup
- **Rationale**:
  - Most common workflow starts with QR scan
  - Allows immediate scanning without clicking
  - USB scanners type and auto-enter
  - Reduces user interaction steps
- **Implementation**: `qr_entry.focus_set()` after GUI build

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

### Motion Controller (Arduino)
- Arduino Uno/Nano/Mega or compatible
- USB connection for serial communication
- Must implement the command protocol (H, R, Z, M commands)
- Must send "DONE\n" after completing movements
- Recommended: Stepper motor with driver (TMC2209, DRV8825, etc.)

### Camera
- USB-C camera or USB webcam
- Minimum resolution: 2560x1920
- Supported by OpenCV VideoCapture
- Windows: DirectShow compatible
- Must support MJPEG or raw frame capture

### Computer
- Windows 10/11 (primary target)
- Python 3.11 or higher
- Available COM port for Arduino
- Available USB port for camera
- Recommended: 8GB+ RAM for high-res preview
- Recommended: Modern CPU for real-time preview

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

- **Current Version**: QR-Code Branch (Latest) - API Integration
  - **QR Code Integration**: Scan QR codes to fetch sample data from M.K. Morse API
  - **API Integration**: Automatic observation creation and image uploads
  - **Non-Blocking Uploads**: Background threading for uploads (inspection runs at full speed)
  - **1-Based Tooth Numbering**: Files and API tags use tooth_0001, tooth_0002, etc.
  - **Auto-Focus QR Field**: QR scan field focused on startup for immediate scanning
  - **Comprehensive API Logging**: All API requests/responses logged to console for debugging
  - **HTTPS Support**: Default API endpoint uses HTTPS with self-signed certificate support
  - Auto-populated teeth count from API sample design
  - Warnings for missing test cases (local-only mode)
  - Git commit: d25f063

- **Previous Version**: Windows Branch
  - Single resolution camera (2560x1920)
  - Flash captured images during inspection
  - Fixed preview sizing issues
  - DirectShow backend support
  - Removed GUI logs panel

- **Earlier Version**: CV-Camera Branch
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
