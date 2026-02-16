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
│  └─────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ├────────────────────┼────────────────────┤
         │                    │                    │
    ┌────▼─────┐       ┌─────▼──────┐      ┌─────▼──────┐
    │ motion.py│       │runner.py   │      │usbc_camera │
    │          │       │            │      │   .py      │
    │ Arduino  │       │ Inspection │      │            │
    │ Control  │       │   Logic    │      │  Camera    │
    └────┬─────┘       └─────┬──────┘      └─────┬──────┘
         │                    │                    │
    ┌────▼─────┐       ┌─────▼──────┐      ┌─────▼──────┐
    │ Arduino  │       │kinematics  │      │  OpenCV /  │
    │ via      │       │    .py     │      │  Physical  │
    │ Serial   │       │            │      │   Camera   │
    │USB/COM   │       │ Angle Math │      └────────────┘
    └──────────┘       └────────────┘
```

## File Descriptions

### **main.py** - GUI Application & Main Controller

**Purpose**: The main entry point and GUI application that orchestrates all system components.

**Key Components**:
- `InspectionGUI` class: Main application window and controller
  - Configuration panel (COM port, teeth count, captures, output directory, camera index)
  - Control buttons (Connect, Hold Motor, Release Motor, Start Inspection, Stop, Exit)
  - Camera preview display with live feed or captured image flash
  - Button state management based on system state

**Key Features**:
- Tkinter-based GUI with maximized window
- Live camera preview at 2560x1920 resolution (~30 FPS when possible)
- During inspection: pauses live preview and flashes each captured image
- Thread-safe operations using `threading.Event` for stop signals
- Automatic button state management (enable/disable based on connection and running states)

**Key Methods**:
- `_toggle_connection()`: Connect/disconnect to Arduino motion controller
- `_hold_motor()`: Enable motor and zero position
- `_release_motor()`: Disable motor
- `_start_inspection()`: Validate inputs and start inspection in background thread
- `_update_preview()`: Continuous camera preview update loop
- `_display_captured_image()`: Flash captured images during inspection
- `_run_inspection_worker()`: Background thread that runs the inspection sequence

**Dependencies**:
- `motion.py`: For Arduino motion controller communication
- `usbc_camera.py`: For camera capture and preview
- `runner.py`: For inspection sequence execution
- `tkinter`: GUI framework
- `PIL`, `cv2`, `numpy`: Image processing

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

### **runner.py** - Inspection Sequence Logic

**Purpose**: Orchestrates the automated inspection sequence - moving the motor and capturing images at each position.

**Key Components**:
- `RunConfig` dataclass: Inspection configuration
  - `teeth`: Number of teeth on the gear
  - `captures`: Number of images to capture
  - `outdir`: Output directory for images
  - `done_timeout_s`: Timeout for each motor movement (default 15.0s)
  - `make_run_subfolder`: Create timestamped subfolder (default True)

- `run_inspection()` function: Main inspection loop
  - Takes motion controller, camera, and callbacks
  - Executes full inspection sequence
  - Returns directory where images were saved

**Inspection Sequence**:
1. Create output directory (with timestamp if `make_run_subfolder=True`)
2. Enable motor hold
3. For each capture (0 to captures-1):
   - Calculate target angle using kinematics
   - Send move command to motor
   - Wait for "DONE" signal (with timeout and stop flag check)
   - Capture image to file
   - Call `on_image_captured` callback (for GUI preview)
   - Log progress
4. Complete and return output directory

**Callbacks**:
- `on_event`: Called with log messages (e.g., "Move 0/59: 0.000000 deg")
- `on_image_captured`: Called with filepath after each capture (for GUI display)

**File Naming Convention**:
```
tooth_<index>_deg_<angle>.png

Examples:
tooth_0000_deg_0.000000.png
tooth_0001_deg_5.000000.png
tooth_0059_deg_295.000000.png
```

**Output Directory Structure**:
```
./captures/
├── run_20260216_143025/
│   ├── tooth_0000_deg_0.000000.png
│   ├── tooth_0001_deg_5.000000.png
│   ├── tooth_0002_deg_10.000000.png
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
```

### 2. **Connection**
```
1. User enters COM port (e.g., COM9)
2. User clicks "Connect"
3. System opens serial connection to Arduino
4. Arduino resets (2 second delay)
5. Serial buffer cleared
6. Status: Connected (button changes to "Disconnect")
```

### 3. **Motor Setup**
```
1. User clicks "Hold Motor"
2. System sends "H\n" command (enable motor)
3. System sends "Z\n" command (zero position)
4. Motor is now holding at position 0.0 degrees
5. Status: Motor enabled and zeroed
```

### 4. **Camera Preview**
```
1. User selects camera index from dropdown
2. User clicks "Connect" (if not already connected)
3. Camera opens with DirectShow backend (Windows)
4. Resolution set to 2560x1920
5. Preview starts at ~30 FPS
6. Images scaled to fit preview area
7. Status: Live preview running
```

### 5. **Inspection Run**
```
1. User sets configuration:
   - Teeth count: 72
   - Captures: 72
   - Output dir: ./captures
   
2. User clicks "Start Inspection"
3. System validates inputs
4. Live preview pauses
5. Creates timestamped output folder
6. For each of 72 captures:
   a. Calculate angle: 0°, 5°, 10°, ... 355°
   b. Send move command: "M5.000000\n"
   c. Wait for "DONE" response (max 15s)
   d. Flush camera buffer (3 frames)
   e. Capture image to PNG
   f. Flash image in preview
   g. Log progress to console
7. Inspection complete
8. Live preview resumes
9. Status: Inspection complete
```

### 6. **Shutdown**
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

---

## Configuration Reference

### Default Values
```python
# Motion Controller
COM_PORT = "COM9"              # Windows: COMx, Linux: /dev/ttyACMx
BAUD_RATE = 115200
CONNECT_DELAY = 2.0            # Arduino reset delay

# Inspection
TEETH_COUNT = 72               # Number of gear teeth
CAPTURES = 72                  # Number of images (typically matches teeth)
OUTPUT_DIR = "./captures"
DONE_TIMEOUT = 15.0            # Max wait time per movement
MAKE_SUBFOLDER = True          # Create timestamped run folders

# Camera
CAMERA_INDEX = 1               # 0, 1, 2, ... (check dropdown)
RESOLUTION = 2560x1920         # Single resolution for preview and capture

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
├── kinematics.py              # Angle calculations
├── requirements.txt           # Python dependencies
├── README.md                  # User guide
├── DOCUMENTATION.md           # This file
└── captures/                  # Output directory (created automatically)
    └── run_YYYYMMDD_HHMMSS/   # Timestamped run folders
        └── tooth_*.png        # Captured images
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

- **Current Version**: Windows Branch (Latest)
  - Single resolution camera (2560x1920)
  - Flash captured images during inspection
  - Fixed preview sizing issues
  - DirectShow backend support
  - Removed GUI logs panel

- **Previous Version**: CV-Camera Branch
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
