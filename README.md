# Auto Teeth Inspection System

Automated teeth inspection system with motor control, camera capture, and API integration for the M.K. Morse Company.

## Features

- **GUI Application**: Modern Tkinter-based interface with status monitoring
- **Auto-Detection**: Automatically detects Dino-Lite camera and ESP32 motor controller
- **QR Code Integration**: Scan sample QR codes to auto-populate teeth count and link to test cases
- **API Integration**: Automatic observation creation and image upload to M.K. Morse testing database
- **Motion Control**: ESP32-based motor controller with health monitoring
- **Health Monitoring**: Continuous motor connection monitoring with automatic reconnection
- **High-Resolution Camera**: Dino-Lite Edge 3.0 at 2560x1920 resolution
- **Automated Inspection**: Captures all teeth automatically with configurable settings
- **Non-Blocking Uploads**: Background image upload with temp file cleanup
- **Windows Optimized**: Uses DirectShow backend for better camera performance
- **Smart Resource Management**: Pauses monitoring during inspection to prevent conflicts

## System Requirements

- Windows 10/11
- Python 3.11 or higher
- Dino-Lite Edge 3.0 USB Camera (auto-detected)
- ESP32-based motion controller with CH340 USB (VID: 0x1A86, PID: 0x55D4)
- USB ports for camera and motor controller

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd auto-teeth-inspection
   ```

2. **Create and activate virtual environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**:
   ```powershell
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. **Configure API (Optional)**:
   Set environment variables for API integration:
   ```powershell
   $env:MKMORSE_API_BASE_URL = "https://eng-ubuntu.mkmorse.local/api"
   ```
   Note: API defaults to `https://eng-ubuntu.mkmorse.local/api` if not set. For local testing, use `http://localhost:8080`.

## Usage

1. **Connect Hardware**:
   - Connect ESP32 motion controller to USB port (auto-detected by VID/PID)
   - Connect Dino-Lite Edge 3.0 camera (auto-detected by name)
   - System will automatically find both devices on startup

2. **Run the application**:
   ```powershell
   .\venv\Scripts\python.exe main.py
   ```

3. **System Status**:
   - **Motor Status Light**: Shows green (connected) or red (disconnected)
   - **Scan Status Light**: Shows green after successful QR scan
   - **Lock/Release Button**: Grayed out when motor disconnected
   - System automatically retries motor connection every 1.5s when disconnected
   - Health check pings motor every 3s when connected

4. **Configure Settings**:
   - **QR Scan**: Scan sample QR code to auto-populate Teeth Count and link to active test case
     - Position cursor in QR Scan field (auto-focused on startup)
     - Scan QR code with USB scanner
     - Press Enter to fetch sample data from API
     - Teeth Count will be automatically populated
     - Scan status light turns green on success
     - If active test case exists, observation will be created during inspection
   - **Teeth Count**: Number of teeth on the gear (auto-populated from QR scan, or set manually)

5. **Operation**:
   - System auto-connects to motor on startup (watch motor status light)
   - Click **Lock** to enable motor and zero position
   - Click **Start/Stop** to toggle automated capture sequence
     - If test case is active, observation will be created automatically
     - Images are captured and uploaded in the background (non-blocking)
     - Temp files are deleted after successful upload
     - System captures one image per tooth (count matches teeth)
     - Images are tagged with tooth numbers (1-based)
     - Motor monitoring pauses during inspection to prevent conflicts
   - Click **Lock/Release** to toggle motor state when done

## File Structure

- `main.py` - GUI application with auto-detection and health monitoring
- `motion.py` - Motion controller interface with ping/pong health checks
- `usbc_camera.py` - Camera interface with auto-detection (pygrabber)
- `runner.py` - Inspection sequence logic with background upload and temp cleanup
- `kinematics.py` - Angle calculation utilities
- `api_client.py` - API client for sample context, observation creation, and image upload
- `testing_funcs.py` - Mock GUI for testing without hardware
- `requirements.txt` - Python dependencies (includes pygrabber>=0.1)

## API Integration

The system integrates with the M.K. Morse testing API to automate observation creation and image upload:

### QR Code Workflow
1. Scan sample QR code (JSON format with identifier)
2. System fetches sample context from API
3. Extracts teeth count and active test case information
4. Auto-populates Teeth Count field
5. Displays test case ID and cut number

### Observation Creation
- When inspection starts, system creates an observation on the active test case
- Observation type: Cut inspection at specified cut number
- If no active test case, inspection runs locally without API upload

### Image Upload
- Each captured tooth image is uploaded to the observation
- Images are tagged with tooth number (1-based: 1, 2, 3, ...)
- Uploads happen in background threads (non-blocking)
- Inspection continues while uploads process
- Upload status logged to console

### API Configuration
```powershell
# Set API base URL (optional, defaults to https://eng-ubuntu.mkmorse.local/api)
$env:MKMORSE_API_BASE_URL = "https://eng-ubuntu.mkmorse.local/api"

# For local testing
$env:MKMORSE_API_BASE_URL = "http://localhost:8080"
```

## Camera Configuration

The system auto-detects Dino-Lite Edge 3.0 cameras:
- **Auto-Detection**: Uses pygrabber to enumerate DirectShow devices
- **Name Matching**: Searches for "dino-lite" or "dinolite" (case-insensitive)
- **Resolution**: 2560x1920 for both preview and capture
- **Preview**: Continuous live feed at ~30 FPS
- **Capture**: High-quality PNG images with 3-frame buffer flush
- **During Inspection**: Live preview pauses, each captured image flashes in preview area

## Motion Controller Protocol

The ESP32 motion controller (CH340 USB) responds to the following commands:
- **Auto-Detection**: Finds ESP32 by VID (0x1A86) and PID (0x55D4)
- `H\n` - Hold/enable motor
- `R\n` - Release/disable motor
- `Z\n` - Zero current position
- `M<degrees>\n` - Move to absolute angle
- `P\n` - Ping for health check
- Controller responds with:
  - `DONE\n` when motion completes
  - `PONG\n` for health check responses

### Health Monitoring
- System automatically pings motor every 3 seconds when connected
- Retries connection every 1.5 seconds when disconnected
- Status light shows green (connected) or red (disconnected)
- Lock/Release button disabled when motor disconnected
- Monitoring pauses during inspection to prevent serial port conflicts

## Output

Images are saved as PNG files with the format:
```
tooth_<number>_deg_<angle>.png
```

where `<number>` starts at 1 (not 0).

Examples:
```
tooth_0001_deg_0.000000.png
tooth_0002_deg_5.000000.png
tooth_0060_deg_295.000000.png
```

### API Integration Mode (Default)
When API integration is enabled:
- Images saved to temporary directory
- Background threads upload each image to observation
- Temp files deleted after successful upload
- Only temp directory remains (cleaned by OS)

### Local-Only Mode
When no test case exists:
- Creates timestamped subfolder: `./captures/run_20260216_143025/`
- Images saved permanently
- No uploads occur
- Files remain for manual review

## Troubleshooting

**Camera not detected**:
- Ensure Dino-Lite Edge 3.0 is properly connected
- Check console output for detected cameras list
- Try different USB ports (USB 3.0 recommended)
- Verify camera name contains "dino-lite" or "dinolite"
- Check camera is not in use by another application

**Motion controller not connecting (red status light)**:
- System auto-detects ESP32 with CH340 USB (VID: 0x1A86, PID: 0x55D4)
- Check console output for "ESP32 (CH340) not found" error
- Verify ESP32 is powered and USB cable is connected
- Wait 2 seconds after connecting for ESP32 to reset
- Check Device Manager for CH340 USB-to-Serial device
- System automatically retries every 1.5 seconds

**Motor status flickering (green/red)**:
- Poor USB connection or cable issue
- ESP32 resetting intermittently
- Try different USB port or cable
- Check power supply stability

**Inspection crashes during run**:
- Should not occur - motor monitoring pauses during inspection
- Check console logs for serial port errors
- Verify ESP32 firmware responds with "DONE\n" after moves
- Ensure Arduino code uses `Serial.println()` with newline characters

**Low preview frame rate**:
- System is optimized for Windows with DirectShow backend
- Single resolution (2560x1920) eliminates camera switching delays
- Modern hardware recommended for 30 FPS preview

## License

Copyright M.K. Morse Company
