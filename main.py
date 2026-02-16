# main.py
from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageTk

from motion import MotionController, MotionConfig
from usbc_camera import USBCCamera
from runner import run_inspection, RunConfig
from api_client import (
    ApiClient, 
    api_config_from_env, 
    extract_teeth_from_context,
    extract_test_case_id_from_context,
    extract_cut_number_from_context
)


class InspectionGUI:
    """
    GUI for teeth inspection system with motor control and camera capture.
    """

    def __init__(self, root: tk.Tk, motion: MotionController, camera: USBCCamera):
        self.root = root
        self.motion = motion
        self.camera = camera

        # Threading
        self.stop_flag = threading.Event()
        self.inspection_thread: Optional[threading.Thread] = None
        self.is_running = False

        # Preview
        self.preview_running = False
        self.preview_label: Optional[tk.Label] = None

        # API / Test Case tracking
        self.sample_context: Optional[dict] = None
        self.test_case_id: Optional[int] = None
        self.cut_number: Optional[int] = None
        self.observation_id: Optional[int] = None

        # Setup window
        self.root.title("Teeth Inspection System")
        
        # Maximize window for full camera preview
        try:
            # Try to maximize window (works on most platforms)
            self.root.state('zoomed')  # Linux/Windows
        except:
            try:
                self.root.attributes('-zoomed', True)  # Alternative for some systems
            except:
                # Fallback: set to 90% of screen size
                screen_width = self.root.winfo_screenwidth()
                screen_height = self.root.winfo_screenheight()
                self.root.geometry(f"{int(screen_width * 0.9)}x{int(screen_height * 0.9)}")
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        self._build_ui()
        self._center_window()
        self._populate_camera_list()
        self._update_button_states()
        
        # Auto-focus QR Scan field
        self.qr_entry.focus_set()

    def _center_window(self):
        """Center the window on screen."""
        self.root.update_idletasks()
        
        # Get window size
        window_width = self.root.winfo_width()
        window_height = self.root.winfo_height()
        
        # Get screen size
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Calculate position
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        # Set position
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

    def _build_ui(self):
        """Build the complete GUI layout."""
        
        # ========== Configuration Frame ==========
        config_frame = ttk.LabelFrame(self.root, text="Configuration", padding=10)
        config_frame.pack(fill=tk.X, padx=10, pady=5)

        # COM Port
        ttk.Label(config_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.port_var = tk.StringVar(value="COM9")
        self.port_entry = ttk.Entry(config_frame, textvariable=self.port_var, width=20)
        self.port_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        # Teeth Count
        ttk.Label(config_frame, text="Teeth Count:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.teeth_var = tk.StringVar(value="72")
        self.teeth_entry = ttk.Entry(config_frame, textvariable=self.teeth_var, width=20)
        self.teeth_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        # Output Directory
        ttk.Label(config_frame, text="Output Dir:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.outdir_var = tk.StringVar(value="./captures")
        self.outdir_entry = ttk.Entry(config_frame, textvariable=self.outdir_var, width=20)
        self.outdir_entry.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        
        self.browse_btn = ttk.Button(config_frame, text="Browse...", command=self._browse_directory)
        self.browse_btn.grid(row=2, column=2, padx=5, pady=2)

        # Camera Index
        ttk.Label(config_frame, text="Camera Index:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.camera_index_var = tk.StringVar(value="0")
        self.camera_index_combo = ttk.Combobox(config_frame, textvariable=self.camera_index_var, width=18, state="readonly")
        self.camera_index_combo.grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)

        # QR Scan
        ttk.Label(config_frame, text="QR Scan:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.qr_var = tk.StringVar(value="")
        self.qr_entry = ttk.Entry(config_frame, textvariable=self.qr_var, width=20)
        self.qr_entry.grid(row=4, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Label(config_frame, text="(scan then press Enter)", foreground="gray").grid(row=4, column=2, sticky=tk.W, padx=5, pady=2)
        self.qr_entry.bind("<Return>", self._on_qr_scanned)

        # ========== Control Buttons Frame ==========
        control_frame = ttk.LabelFrame(self.root, text="Controls", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        # First row: Connect, Hold, Release
        btn_row1 = ttk.Frame(control_frame)
        btn_row1.pack(fill=tk.X, pady=2)

        self.connect_btn = ttk.Button(btn_row1, text="Connect", command=self._toggle_connection, width=15)
        self.connect_btn.pack(side=tk.LEFT, padx=5)

        self.hold_btn = ttk.Button(btn_row1, text="Hold Motor", command=self._hold_motor, width=15)
        self.hold_btn.pack(side=tk.LEFT, padx=5)

        self.release_btn = ttk.Button(btn_row1, text="Release Motor", command=self._release_motor, width=15)
        self.release_btn.pack(side=tk.LEFT, padx=5)

        # Second row: Start, Stop, Exit
        btn_row2 = ttk.Frame(control_frame)
        btn_row2.pack(fill=tk.X, pady=2)

        self.start_btn = ttk.Button(btn_row2, text="Start Inspection", command=self._start_inspection, width=15)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(btn_row2, text="Stop", command=self._stop_inspection, width=15)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        self.exit_btn = ttk.Button(btn_row2, text="Exit", command=self._on_closing, width=15)
        self.exit_btn.pack(side=tk.LEFT, padx=5)

        # ========== Camera Preview (Square) ==========
        preview_frame = ttk.LabelFrame(self.root, text="Camera Preview", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create container for camera preview - use fill=BOTH to expand properly
        self.preview_label = tk.Label(preview_frame, bg="black")
        self.preview_label.pack(fill=tk.BOTH, expand=True)

    def _populate_camera_list(self):
        """Populate the camera index dropdown with available cameras."""
        try:
            available = USBCCamera.list_available_cameras(max_index=10)
            if available:
                self.camera_index_combo['values'] = [str(i) for i in available]
                self.camera_index_var.set(str(available[0]))
            else:
                self.camera_index_combo['values'] = ['0']
                self.camera_index_var.set('0')
        except Exception as e:
            self._log(f"⚠ Could not detect cameras: {e}")
            self.camera_index_combo['values'] = ['0']
            self.camera_index_var.set('0')

    def _browse_directory(self):
        """Open directory browser dialog."""
        directory = filedialog.askdirectory(initialdir=self.outdir_var.get())
        if directory:
            self.outdir_var.set(directory)

    def _on_qr_scanned(self, event=None):
        """Handle QR code scan completion."""
        qr_data = self.qr_var.get().strip()
        self.qr_var.set("")  # Clear field for next scan
        
        if not qr_data:
            return
        
        # Try to parse as JSON to extract identifier
        identifier = qr_data
        try:
            parsed = json.loads(qr_data)
            if isinstance(parsed, dict) and "identifier" in parsed:
                identifier = parsed["identifier"]
                self._log(f"Parsed QR code: type={parsed.get('type', 'N/A')}, identifier={identifier}")
        except (json.JSONDecodeError, ValueError):
            # Not JSON, use as-is
            self._log(f"Using QR code as identifier: {identifier}")
        
        # Get API configuration
        api_config = api_config_from_env()
        
        # Fetch sample context in background thread
        def worker():
            try:
                client = ApiClient(api_config)
                self._log(f"Fetching sample context for: {identifier}")
                context = client.get_sample_context(identifier)
                teeth = extract_teeth_from_context(context)
                test_case_id = extract_test_case_id_from_context(context)
                cut_number = extract_cut_number_from_context(context)
                
                # Update GUI on main thread
                def update_gui():
                    # Store context data
                    self.sample_context = context
                    self.test_case_id = test_case_id
                    self.cut_number = cut_number
                    
                    # Update teeth count
                    self.teeth_var.set(str(teeth))
                    self._log(f"Auto-populated Teeth Count: {teeth}")
                    
                    # Warn if no active test case
                    if test_case_id is None:
                        self._log("⚠ Warning: No active test case found - inspection will run locally without API upload")
                    else:
                        self._log(f"✓ Test Case ID: {test_case_id}, Cut Number: {cut_number}")
                
                self.root.after(0, update_gui)
                
            except Exception as e:
                # Capture error message before nested function
                error_msg = str(e)
                
                # Log error on main thread
                def log_error():
                    self._log(f"Error fetching sample context: {error_msg}")
                
                self.root.after(0, log_error)
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _log(self, message: str):
        """Log message to console (no GUI log panel)."""
        print(message)

    def _update_button_states(self):
        """Update button enabled/disabled states based on connection and running status."""
        connected = self.motion.is_connected
        running = self.is_running

        # Connection button always enabled
        self.connect_btn.config(text="Disconnect" if connected else "Connect")

        # Motor controls only when connected and not running
        state_motor = tk.NORMAL if (connected and not running) else tk.DISABLED
        self.hold_btn.config(state=state_motor)
        self.release_btn.config(state=state_motor)

        # Start only when connected and not running
        state_start = tk.NORMAL if (connected and not running) else tk.DISABLED
        self.start_btn.config(state=state_start)

        # Stop only when running
        state_stop = tk.NORMAL if running else tk.DISABLED
        self.stop_btn.config(state=state_stop)

        # Config fields only when not running
        state_config = tk.NORMAL if not running else tk.DISABLED
        self.port_entry.config(state=state_config)
        self.teeth_entry.config(state=state_config)
        self.outdir_entry.config(state=state_config)
        self.browse_btn.config(state=state_config)
        
        # Camera index only when not connected and not running
        state_camera = "readonly" if not (connected or running) else tk.DISABLED
        self.camera_index_combo.config(state=state_camera)

    def _toggle_connection(self):
        """Connect or disconnect from motion controller."""
        try:
            if self.motion.is_connected:
                # Stop preview first
                self.preview_running = False
                
                # Disconnect
                self.motion.close()
                self.camera.close()
                self._log("✓ Disconnected from motion controller and camera")
                
                # Clear preview
                self.preview_label.config(image='', text='Camera Disconnected', fg='white')
            else:
                # Connect
                port = self.port_var.get().strip()
                if not port:
                    messagebox.showerror("Error", "Please enter a COM port")
                    return

                # Update camera device index from dropdown
                try:
                    camera_index = int(self.camera_index_var.get())
                    self.camera.device_index = camera_index
                except ValueError:
                    messagebox.showerror("Error", "Invalid camera index")
                    return

                config = MotionConfig(port=port)
                self.motion.cfg = config
                self.motion.connect()
                self.camera.open()
                self._log(f"✓ Connected to {port} and opened camera {camera_index}")
                
                # Start preview
                self.preview_running = True
                self._update_preview()

        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect: {e}")
            self._log(f"✗ Connection failed: {e}")
        finally:
            self._update_button_states()

    def _hold_motor(self):
        """Send hold command to motor."""
        try:
            self.motion.hold()
            self._log("✓ Motor hold enabled")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to hold motor: {e}")
            self._log(f"✗ Hold failed: {e}")
        
        try:
            self.motion.zero()
            self._log("✓ Motor zeroed")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to zero motor: {e}")
            self._log(f"✗ Zero failed: {e}")

    def _release_motor(self):
        """Send release command to motor."""
        try:
            self.motion.release()
            self._log("✓ Motor released")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to release motor: {e}")
            self._log(f"✗ Release failed: {e}")

    def _update_preview(self):
        """Update camera preview display (runs continuously via after() callbacks)."""
        if not self.preview_running or not self.camera.is_open:
            return

        try:
            success, frame = self.camera.read_frame()
            
            if success and frame is not None:
                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Resize to fit preview area (dynamic based on window size)
                height, width = frame_rgb.shape[:2]
                
                # Get available space in preview area
                preview_width = self.preview_label.winfo_width()
                preview_height = self.preview_label.winfo_height()
                
                # Use larger defaults if widget hasn't been sized yet
                # Assume reasonable window size for preview area
                max_width = preview_width if preview_width > 100 else 1000
                max_height = preview_height if preview_height > 100 else 800
                
                # Calculate scaling factor to maintain aspect ratio
                scale = min(max_width / width, max_height / height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                
                # Ensure minimum size to prevent tiny preview
                if new_width < 400:
                    new_width = min(800, width)
                    new_height = int(height * (new_width / width))
                
                frame_resized = cv2.resize(frame_rgb, (new_width, new_height))
                
                # Convert to PhotoImage
                img = Image.fromarray(frame_resized)
                photo = ImageTk.PhotoImage(image=img)
                
                # Update label
                self.preview_label.config(image=photo, text='')
                self.preview_label.image = photo  # Keep reference to avoid GC
            else:
                # Show error message
                self.preview_label.config(image='', text='No Camera Signal', fg='red')
                
        except Exception as e:
            self.preview_label.config(image='', text=f'Preview Error: {e}', fg='red')
        
        # Schedule next update (~30 FPS)
        if self.preview_running:
            self.root.after(33, self._update_preview)

    def _display_captured_image(self, filepath: str):
        """Display a captured image in the preview (thread-safe)."""
        def update():
            try:
                # Load the captured image
                img = Image.open(filepath)
                img_array = np.array(img)
                
                # Convert BGR to RGB if needed
                if len(img_array.shape) == 3 and img_array.shape[2] == 3:
                    img_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
                else:
                    img_rgb = img_array
                
                # Resize to fit preview area
                height, width = img_rgb.shape[:2]
                preview_width = self.preview_label.winfo_width()
                preview_height = self.preview_label.winfo_height()
                
                max_width = preview_width if preview_width > 100 else 1000
                max_height = preview_height if preview_height > 100 else 800
                
                scale = min(max_width / width, max_height / height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                
                if new_width < 400:
                    new_width = min(800, width)
                    new_height = int(height * (new_width / width))
                
                img_resized = cv2.resize(img_rgb, (new_width, new_height))
                
                # Convert to PhotoImage
                img_pil = Image.fromarray(img_resized)
                photo = ImageTk.PhotoImage(image=img_pil)
                
                # Update label
                self.preview_label.config(image=photo, text='')
                self.preview_label.image = photo
            except Exception as e:
                self._log(f"Failed to display image: {e}")
        
        # Schedule update on main thread
        self.root.after(0, update)

    def _start_inspection(self):
        """Start inspection run in background thread."""
        try:
            # Validate inputs
            teeth = int(self.teeth_var.get())
            captures = teeth  # Capture all teeth
            outdir = self.outdir_var.get().strip()

            if teeth <= 0:
                messagebox.showerror("Error", "Teeth count must be > 0")
                return
            if not outdir:
                messagebox.showerror("Error", "Please specify output directory")
                return

            # Create observation if test case is available
            observation_id = None
            api_config = None
            
            if self.test_case_id is not None:
                try:
                    api_config = api_config_from_env()
                    client = ApiClient(api_config)
                    
                    # Determine scope: "incoming" if cut_number is 0 or None, otherwise "cut"
                    # Treat None as 0 for the API (incoming inspection)
                    cut_num = self.cut_number if self.cut_number is not None else 0
                    scope = "incoming" if (self.cut_number is None or self.cut_number == 0) else "cut"
                    
                    self._log(f"Creating observation for test case {self.test_case_id} (scope: {scope}, cut: {cut_num})...")
                    obs_response = client.create_observation(self.test_case_id, cut_num, scope=scope)
                    
                    # Validate response
                    if obs_response is None:
                        raise ValueError("API returned None response")
                    if not isinstance(obs_response, dict):
                        raise ValueError(f"API returned unexpected type: {type(obs_response)}")
                    
                    observation_id = obs_response.get("id")
                    if observation_id is None:
                        raise ValueError(f"No 'id' in observation response: {obs_response}")
                    
                    self.observation_id = observation_id
                    self._log(f"✓ Created observation ID: {observation_id}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to create observation: {e}")
                    return
            else:
                self._log("⚠ No test case - running inspection locally without API upload")

            # Set up run
            self.is_running = True
            self.stop_flag.clear()
            
            # Pause live preview during inspection
            self.preview_running = False
            
            self._update_button_states()

            config = RunConfig(
                teeth=teeth,
                captures=captures,
                outdir=outdir,
                done_timeout_s=15.0,
                make_run_subfolder=True,
                observation_id=observation_id,
                api_config=api_config
            )

            self._log("=" * 60)
            self._log(f"Starting inspection: {captures} captures of {teeth} teeth")
            self._log("=" * 60)

            # Run in background thread
            self.inspection_thread = threading.Thread(
                target=self._run_inspection_worker,
                args=(config,),
                daemon=True
            )
            self.inspection_thread.start()

        except ValueError as e:
            messagebox.showerror("Error", f"Invalid input: {e}")
            self.is_running = False
            self._update_button_states()

    def _run_inspection_worker(self, config: RunConfig):
        """Worker thread for running inspection."""
        try:
            result_dir = run_inspection(
                cfg=config,
                motion=self.motion,
                camera=self.camera,
                stop_flag=self.stop_flag,
                on_event=self._log,
                on_image_captured=self._display_captured_image
            )
            self._log("=" * 60)
            self._log(f"✓ Inspection complete: {result_dir}")
            self._log("=" * 60)
        except Exception as e:
            self._log(f"✗ Inspection failed: {e}")
            messagebox.showerror("Inspection Error", f"Failed: {e}")
        finally:
            self.is_running = False
            # Resume live preview
            if self.camera.is_open:
                self.preview_running = True
                self.root.after(0, self._update_preview)
            self.root.after(0, self._update_button_states)

    def _stop_inspection(self):
        """Signal inspection to stop."""
        self._log("⚠ Stop requested...")
        self.stop_flag.set()

    def _on_closing(self):
        """Handle window close event."""
        if self.is_running:
            if not messagebox.askyesno("Confirm Exit", "Inspection is running. Stop and exit?"):
                return
            self.stop_flag.set()

        # Stop preview
        self.preview_running = False

        # Cleanup
        try:
            self.motion.close()
            self.camera.close()
        except Exception:
            pass

        self.root.destroy()


def main():
    """Entry point for the teeth inspection application."""
    # Create motion controller (not connected yet)
    motion = MotionController(cfg=MotionConfig(port=""))

    # Create USB-C camera (not opened yet)
    camera = USBCCamera(device_index=1)

    # Create GUI
    root = tk.Tk()
    app = InspectionGUI(root, motion, camera)

    # Run main loop
    root.mainloop()


if __name__ == "__main__":
    main()
