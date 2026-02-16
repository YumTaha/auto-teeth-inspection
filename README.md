# Auto Teeth Inspection System

Automated teeth inspection system with motor control and camera capture for the M.K. Morse Company.

## Features

- **GUI Application**: Tkinter-based interface for easy operation
- **Motion Control**: Arduino-based motor controller for precise positioning
- **High-Resolution Camera**: USB-C camera with dual resolution support
  - Preview: 1280x960 for smooth live view
  - Capture: 2560x1920 for high-quality inspection images
- **Automated Inspection**: Configurable number of captures with automatic rotation
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
   .\venv\Scripts\python.exe
   ```

3. **Install dependencies**:
   ```powershell
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

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
   - **Teeth Count**: Number of teeth on the gear (default: 60)
   - **Captures**: Number of images to capture (default: 60)
   - **Output Dir**: Directory to save captured images (default: ./captures)
   - **Camera Index**: Select your USB-C camera from dropdown

4. **Operation**:
   - Click **Connect** to connect to motion controller
   - Click **Hold Motor** to enable motor and zero position
   - Click **Start Inspection** to begin automated capture sequence
   - Click **Stop** to halt inspection if needed
   - Click **Release Motor** to disable motor when done

## File Structure

- `main.py` - GUI application and main entry point
- `motion.py` - Motion controller interface (serial communication)
- `usbc_camera.py` - Camera interface with dual resolution support
- `runner.py` - Inspection sequence logic
- `kinematics.py` - Angle calculation utilities
- `requirements.txt` - Python dependencies

## Camera Configuration

The system uses dual resolution strategy:
- **Preview Mode**: 1280x960 resolution for real-time preview (smooth 30 FPS)
- **Capture Mode**: 2560x1920 resolution for high-quality images

The camera automatically switches between resolutions during operation.

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
tooth_<index>_deg_<angle>.png
```

Each run creates a timestamped subfolder in the output directory.

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
