# Auto Teeth Inspection System

Automated teeth inspection system with motor control, camera capture, and API integration for the M.K. Morse Company.

## Features

- **GUI Application**: Tkinter-based interface for easy operation
- **QR Code Integration**: Scan sample QR codes to auto-populate teeth count and link to test cases
- **API Integration**: Automatic observation creation and image upload to M.K. Morse testing database
- **Motion Control**: Arduino-based motor controller for precise positioning
- **High-Resolution Camera**: USB-C camera at 2560x1920 resolution
- **Automated Inspection**: Captures all teeth automatically with configurable settings
- **Non-Blocking Uploads**: Background image upload for fast inspection workflow
- **Windows Optimized**: Uses DirectShow backend for better camera performance

## System Requirements

- Windows 10/11
- Python 3.11 or higher
- USB-C Camera
- Arduino-based motion controller
- Available COM port for serial communication

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
   - Connect Arduino motion controller to USB port (note the COM port number)
   - Connect USB-C camera

2. **Run the application**:
   ```powershell
   .\venv\Scripts\python.exe main.py
   ```

3. **Configure Settings**:
   - **COM Port**: Set to your Arduino's COM port (e.g., COM3, COM4)
   - **QR Scan**: Scan sample QR code to auto-populate Teeth Count and link to active test case
     - Position cursor in QR Scan field (auto-focused on startup)
     - Scan QR code with USB scanner
     - Press Enter to fetch sample data from API
     - Teeth Count will be automatically populated
     - If active test case exists, observation will be created during inspection
   - **Teeth Count**: Number of teeth on the gear (auto-populated from QR scan, or set manually)
   - **Output Dir**: Directory to save captured images (default: ./captures)
   - **Camera Index**: Select your USB-C camera from dropdown

4. **Operation**:
   - Click **Connect** to connect to motion controller
   - Click **Hold Motor** to enable motor and zero position
   - Click **Start Inspection** to begin automated capture sequence
     - If test case is active, observation will be created automatically
     - Images are captured and uploaded in the background (non-blocking)
     - System captures one image per tooth (count matches teeth)
     - Images are tagged with tooth numbers (1-based)
   - Click **Stop** to halt inspection if needed
   - Click **Release Motor** to disable motor when done

## File Structure

- `main.py` - GUI application and main entry point
- `motion.py` - Motion controller interface (serial communication)
- `usbc_camera.py` - Camera interface with 2560x1920 resolution
- `runner.py` - Inspection sequence logic with background upload
- `kinematics.py` - Angle calculation utilities
- `api_client.py` - API client for sample context, observation creation, and image upload
- `requirements.txt` - Python dependencies

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

The system uses single resolution strategy:
- **Resolution**: 2560x1920 for both preview and capture
- **Preview**: Continuous live feed at ~30 FPS
- **Capture**: High-quality PNG images
- **During Inspection**: Live preview pauses, each captured image flashes in preview area

## Motion Controller Protocol

The Arduino motion controller responds to the following commands:
- `H\n` - Hold/enable motor
- `R\n` - Release/disable motor
- `Z\n` - Zero current position
- `M<degrees>\n` - Move to absolute angle
- Arduino responds with `DONE\n` when motion completes

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

Each run creates a timestamped subfolder in the output directory:
```
./captures/
├── run_20260216_143025/
│   ├── tooth_0001_deg_0.000000.png
│   ├── tooth_0002_deg_5.000000.png
│   └── ...
└── run_20260216_144532/
    └── ...
```

If API integration is enabled, images are also uploaded to the observation with tooth number tags.

## Troubleshooting

**Camera not detected**:
- Ensure USB-C camera is properly connected
- Try different USB ports
- Check camera is not in use by another application

**Motion controller not connecting**:
- Verify correct COM port in Device Manager
- Check Arduino is powered and serial cable is connected
- Wait 2-3 seconds after connecting for Arduino to reset

**Low preview frame rate**:
- System is optimized for Windows with DirectShow backend
- Preview resolution is automatically set to 1280x960 for smooth performance
- High-quality captures still use 2560x1920 resolution

## License

Copyright M.K. Morse Company
