# test.py
from __future__ import annotations

import json
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox
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
    extract_cut_number_from_context,
)


# ==============================
# CONFIG (change here)
# ==============================
CAMERA_INDEX = 0          # <- change if wrong camera
MOTOR_PORT = "COM4"       # <- change as needed
PREVIEW_FPS = 30
SIDE_WIDTH = 320
MOTOR_RETRY_MS = 1500     # retry motor connection every N ms
# ==============================


class InspectionGUI(tk.Tk):
    def __init__(self, motion: MotionController, camera: USBCCamera):
        super().__init__()
        self.title("AUTO TOOTH INSPECTION")
        self.configure(bg="#1f1f1f")
        self.state("zoomed")

        self.motion = motion
        self.camera = camera

        # state
        self.stop_flag = threading.Event()
        self.run_thread: Optional[threading.Thread] = None
        self.is_running = False

        self.scan_ok = False
        self.blade_locked = False

        # motor gating + overlay
        self.motor_connected = False
        self._motor_retry_job = None

        # API / Test Case tracking
        self.sample_context: Optional[dict] = None
        self.test_case_id: Optional[int] = None
        self.cut_number: Optional[int] = None
        self.observation_id: Optional[int] = None
        self.teeth_count: int = 72  # default

        # camera preview
        self.preview_running = False
        self._last_photo = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_styles()
        self._build_layout()
        self._install_invisible_qr_entry()
        self._build_motor_overlay()

        # Auto-connect
        self.after(50, self._auto_connect)

    # -------------------------
    # Overlay (motor required)
    # -------------------------
    def _build_motor_overlay(self):
        """Grey-out overlay shown when motor isn't connected."""
        self.motor_overlay = tk.Frame(self, bg="#0b0b0b")
        # "Card" in the center
        card = tk.Frame(self.motor_overlay, bg="#2a2a2a", bd=0, highlightthickness=0)
        card.place(relx=0.5, rely=0.5, anchor="center", width=440, height=200)

        tk.Label(
            card,
            text="CONNECT THE MOTOR",
            bg="#2a2a2a",
            fg="#f5f5f5",
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=(18, 8))

        self.motor_overlay_msg = tk.Label(
            card,
            text=f"Please connect the motor on {MOTOR_PORT}.",
            bg="#2a2a2a",
            fg="#d1d5db",
            font=("Segoe UI", 11),
            wraplength=400,
            justify="center",
        )
        self.motor_overlay_msg.pack(pady=(0, 12))

        ttk.Button(card, text="Retry", command=self._retry_motor_connect_once).pack()

        # start hidden
        self.motor_overlay.place_forget()

    def _show_motor_overlay(self, msg: str | None = None):
        if msg:
            self.motor_overlay_msg.config(text=msg)
        self.motor_overlay.place(x=0, y=0, relwidth=1, relheight=1)
        self.motor_overlay.lift()
        self.motor_overlay.focus_set()

    def _hide_motor_overlay(self):
        self.motor_overlay.place_forget()

    def _retry_motor_connect_once(self):
        threading.Thread(target=self._motor_connect_worker, daemon=True).start()

    def _start_motor_retry_loop(self):
        if self._motor_retry_job is not None:
            try:
                self.after_cancel(self._motor_retry_job)
            except Exception:
                pass
            self._motor_retry_job = None

        def tick():
            if not self.motor_connected:
                threading.Thread(target=self._motor_connect_worker, daemon=True).start()
                self._motor_retry_job = self.after(MOTOR_RETRY_MS, tick)
            else:
                self._motor_retry_job = None

        self._motor_retry_job = self.after(10, tick)

    def _motor_connect_worker(self):
        try:
            if not self.motion.is_connected:
                self.motion.connect()

            self.motor_connected = True
            self.after(0, lambda: self._set_motor_light(True, f"Connected ({MOTOR_PORT})"))
            self.after(0, self._hide_motor_overlay)

        except Exception as e:
            self.motor_connected = False
            err = str(e)
            self.after(0, lambda: self._set_motor_light(False, f"Not connected ({MOTOR_PORT})"))
            self.after(
                0,
                lambda m=err: self._show_motor_overlay(
                    f"Please connect the motor on {MOTOR_PORT}.\n\n{m}"
                ),
            )

    # -------------------------
    # UI setup
    # -------------------------
    def _build_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background="#1f1f1f")
        style.configure("Panel.TFrame", background="#2a2a2a")
        style.configure("Title.TLabel", background="#2a2a2a", foreground="#f5f5f5", font=("Segoe UI", 12, "bold"))
        style.configure("TLabel", background="#2a2a2a", foreground="#f5f5f5", font=("Segoe UI", 11))

        style.configure("Primary.TButton", font=("Segoe UI", 12, "bold"), padding=(16, 12),
                        background="#2563eb", foreground="#ffffff", borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#1d4ed8")])

        style.configure("Danger.TButton", font=("Segoe UI", 12, "bold"), padding=(16, 12),
                        background="#dc2626", foreground="#ffffff", borderwidth=0)
        style.map("Danger.TButton", background=[("active", "#b91c1c")])

        style.configure("Neutral.TButton", font=("Segoe UI", 12, "bold"), padding=(16, 12),
                        background="#404040", foreground="#ffffff", borderwidth=0)
        style.map("Neutral.TButton", background=[("active", "#525252")])

        style.configure("Disabled.TButton", font=("Segoe UI", 12, "bold"), padding=(16, 12),
                        background="#3a3a3a", foreground="#9ca3af", borderwidth=0)

    def _build_layout(self):
        # root layout
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        container = ttk.Frame(self, style="App.TFrame", padding=12)
        container.grid(row=0, column=0, columnspan=2, sticky="nsew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=0, minsize=SIDE_WIDTH)
        container.grid_columnconfigure(1, weight=1)

        # -------------------------
        # Side panel
        # -------------------------
        side = ttk.Frame(container, style="Panel.TFrame", padding=12, width=SIDE_WIDTH)
        side.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        side.grid_propagate(False)

        ttk.Label(side, text="INFO", style="Title.TLabel").pack(anchor="w")

        # API data fields
        self.name_var = tk.StringVar(value="Name: -")
        self.teeth_var = tk.StringVar(value="Teeth: -")
        self.blade_count_var = tk.StringVar(value="Blade count: -")
        self.test_case_var = tk.StringVar(value="Test case: -")
        self.cut_number_var = tk.StringVar(value="Cut: -")

        ttk.Label(side, textvariable=self.name_var).pack(anchor="w", pady=(10, 0))
        ttk.Label(side, textvariable=self.teeth_var).pack(anchor="w", pady=(4, 0))
        ttk.Label(side, textvariable=self.blade_count_var).pack(anchor="w", pady=(4, 0))
        ttk.Label(side, textvariable=self.test_case_var).pack(anchor="w", pady=(4, 0))
        ttk.Label(side, textvariable=self.cut_number_var).pack(anchor="w", pady=(4, 0))

        # Instructions section
        ttk.Label(side, text="INSTRUCTIONS", style="Title.TLabel").pack(anchor="w", pady=(18, 6))
        self.instructions_var = tk.StringVar(value="SCAN QR CODE ON BLADE")
        ttk.Label(side, textvariable=self.instructions_var, wraplength=280).pack(anchor="w")

        # Scan status light
        ttk.Label(side, text="SCAN STATUS", style="Title.TLabel").pack(anchor="w", pady=(18, 6))
        light_row = ttk.Frame(side, style="Panel.TFrame")
        light_row.pack(anchor="w")

        self.light = tk.Canvas(light_row, width=18, height=18, bg="#2a2a2a", highlightthickness=0)
        self.light.pack(side="left")
        self.light_dot = self.light.create_oval(2, 2, 16, 16, fill="#dc2626", outline="")  # red default
        self.light_label = ttk.Label(light_row, text="Waiting for scan...")
        self.light_label.pack(side="left", padx=(8, 0))

        # Motor status light
        ttk.Label(side, text="MOTOR STATUS", style="Title.TLabel").pack(anchor="w", pady=(18, 6))
        motor_row = ttk.Frame(side, style="Panel.TFrame")
        motor_row.pack(anchor="w")

        self.motor_light = tk.Canvas(motor_row, width=18, height=18, bg="#2a2a2a", highlightthickness=0)
        self.motor_light.pack(side="left")
        self.motor_light_dot = self.motor_light.create_oval(2, 2, 16, 16, fill="#dc2626", outline="")  # red default
        self.motor_light_label = ttk.Label(motor_row, text=f"Not connected ({MOTOR_PORT})")
        self.motor_light_label.pack(side="left", padx=(8, 0))

        # -------------------------
        # Camera area
        # -------------------------
        cam_wrap = ttk.Frame(container, style="Panel.TFrame", padding=12)
        cam_wrap.grid(row=0, column=1, sticky="nsew")
        cam_wrap.grid_rowconfigure(0, weight=1)
        cam_wrap.grid_columnconfigure(0, weight=1)

        self.preview_label = tk.Label(cam_wrap, bg="#0f172a")
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        # -------------------------
        # Bottom buttons (ONLY 2)
        # -------------------------
        bottom = ttk.Frame(self, style="App.TFrame", padding=(12, 0, 12, 12))
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)

        self.lock_btn = ttk.Button(bottom, text="LOCK BLADE", style="Neutral.TButton", command=self._toggle_blade_lock)
        self.lock_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=10)

        self.start_btn = ttk.Button(bottom, text="START INSPECTION", style="Disabled.TButton",
                                    state="disabled", command=self._start_or_stop)
        self.start_btn.grid(row=0, column=1, sticky="ew", padx=(8, 0), ipady=10)

        self._update_button_states()

    def _install_invisible_qr_entry(self):
        # Invisible QR entry: always focused on click/focus
        self.qr_var = tk.StringVar(value="")
        self.qr_entry = ttk.Entry(self, textvariable=self.qr_var)
        self.qr_entry.place(x=-5000, y=-5000, width=1, height=1)
        self.qr_entry.bind("<Return>", self._on_qr_scanned)
        self.qr_entry.bind("<KP_Enter>", self._on_qr_scanned)

        # Whenever user clicks the app window, refocus
        self.bind("<Button-1>", self._refocus_qr, add=True)
        self.bind("<FocusIn>", self._refocus_qr, add=True)

        self.after(50, self._refocus_qr)

    def _refocus_qr(self, event=None):
        try:
            self.qr_entry.focus_set()
        except Exception:
            pass

    def _log(self, message: str):
        """Log message to console."""
        print(message)

    # -------------------------
    # Auto connect + preview
    # -------------------------
    def _auto_connect(self):
        def worker():
            # Motor connection (required)
            threading.Thread(target=self._motor_connect_worker, daemon=True).start()
            self.after(0, self._start_motor_retry_loop)

            # Camera open (independent; always try)
            try:
                if not self.camera.is_open:
                    self.camera.open()
                self.after(0, self._start_preview_loop)
            except Exception as e:
                cam_msg = str(e)
                self.after(0, lambda c=cam_msg: self.preview_label.config(
                    text=f"Camera failed to open.\n{c}",
                    fg="white",
                    bg="#111827",
                    font=("Segoe UI", 14),
                ))
                print(f"[CAMERA] open failed: {cam_msg}")

            # Always refocus QR
            self.after(0, self._refocus_qr)

        threading.Thread(target=worker, daemon=True).start()

    def _start_preview_loop(self):
        if self.preview_running:
            return
        self.preview_running = True
        self._update_preview()

    def _update_preview(self):
        if not self.preview_running or not self.camera.is_open:
            return

        try:
            ok, frame = self.camera.read_frame()
            if ok and frame is not None:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                h, w = frame_rgb.shape[:2]
                target_w = max(1, self.preview_label.winfo_width())
                target_h = max(1, self.preview_label.winfo_height())

                if target_w < 50 or target_h < 50:
                    target_w, target_h = w, h

                frame_resized = cv2.resize(frame_rgb, (target_w, target_h), interpolation=cv2.INTER_AREA)

                img = Image.fromarray(frame_resized)
                photo = ImageTk.PhotoImage(img)

                self.preview_label.config(image=photo)
                self._last_photo = photo
            else:
                self.preview_label.config(text="No Camera Signal", fg="white", bg="#111827", font=("Segoe UI", 14))

        except Exception as e:
            self.preview_label.config(text=f"Preview error:\n{e}", fg="white", bg="#111827", font=("Segoe UI", 14))

        self.after(int(1000 / PREVIEW_FPS), self._update_preview)

    # -------------------------
    # Scan flow (invisible entry + Enter)
    # -------------------------
    def _on_qr_scanned(self, event=None):
        if self.is_running:
            return

        identifier = self.qr_var.get().strip()
        self.qr_var.set("")
        if not identifier:
            self._refocus_qr()
            return

        self.instructions_var.set("Scanning...")
        self._set_light(False, "Scanning...")

        threading.Thread(target=self._handle_scan_worker, args=(identifier,), daemon=True).start()

    def _handle_scan_worker(self, identifier: str):
        """Fetch real API context from M.K. Morse system."""
        try:
            # Try to parse as JSON to extract identifier
            parsed_identifier = identifier
            try:
                parsed = json.loads(identifier)
                if isinstance(parsed, dict) and "identifier" in parsed:
                    parsed_identifier = parsed["identifier"]
                    self._log(f"Parsed QR code: type={parsed.get('type', 'N/A')}, identifier={parsed_identifier}")
            except (json.JSONDecodeError, ValueError):
                self._log(f"Using QR code as identifier: {parsed_identifier}")

            # Get API configuration
            api_config = api_config_from_env()
            client = ApiClient(api_config)
            
            self._log(f"Fetching sample context for: {parsed_identifier}")
            context = client.get_sample_context(parsed_identifier)
            
            # Extract data from context
            teeth = extract_teeth_from_context(context)
            test_case_id = extract_test_case_id_from_context(context)
            cut_number = extract_cut_number_from_context(context)
            
            # Extract additional info
            sample_name = context.get("sample", {}).get("identifier", "-")
            design_name = context.get("sample", {}).get("design", {}).get("name", "-")
            
            # Get blade count (total cuts + 1 for incoming)
            blade_count = (cut_number or 0) + 1

            def apply_success():
                self.scan_ok = True
                self.sample_context = context
                self.test_case_id = test_case_id
                self.cut_number = cut_number
                self.teeth_count = teeth
                
                # Update INFO panel
                self.name_var.set(f"Name: {design_name}")
                self.teeth_var.set(f"Teeth: {teeth}")
                self.blade_count_var.set(f"Blade count: {blade_count}")
                self.test_case_var.set(f"Test case: {test_case_id if test_case_id else 'None'}")
                self.cut_number_var.set(f"Cut: {cut_number if cut_number is not None else 'Incoming'}")

                self._set_light(True, "Scan OK")
                
                # Warn if no active test case
                if test_case_id is None:
                    self._log("⚠ Warning: No active test case found")
                    self.instructions_var.set("⚠ No test case - cannot upload. Scan different QR.")
                elif self.blade_locked:
                    self.instructions_var.set("Press START INSPECTION.")
                else:
                    self.instructions_var.set("Lock the blade, then press START INSPECTION.")

                self._update_button_states()
                self._refocus_qr()

            self.after(0, apply_success)

        except Exception as e:
            error_msg = str(e)
            self._log(f"Error fetching sample context: {error_msg}")

            def apply_error():
                self.scan_ok = False
                self.sample_context = None
                self.test_case_id = None
                self.cut_number = None
                
                self.name_var.set("Name: -")
                self.teeth_var.set("Teeth: -")
                self.blade_count_var.set("Blade count: -")
                self.test_case_var.set("Test case: -")
                self.cut_number_var.set("Cut: -")

                self._set_light(False, f"Scan FAILED")
                self.instructions_var.set(f"SCAN FAILED: {error_msg[:50]}")

                self._update_button_states()
                self._refocus_qr()

            self.after(0, apply_error)

    def _set_light(self, ok: bool, text: str):
        self.light.itemconfig(self.light_dot, fill=("#16a34a" if ok else "#dc2626"))
        self.light_label.config(text=text)

    def _set_motor_light(self, ok: bool, text: str):
        self.motor_light.itemconfig(self.motor_light_dot, fill=("#16a34a" if ok else "#dc2626"))
        self.motor_light_label.config(text=text)

    # -------------------------
    # Blade lock + run control
    # -------------------------
    def _toggle_blade_lock(self):
        if self.is_running:
            return

        self.blade_locked = not self.blade_locked
        
        if self.blade_locked:
            # Lock: hold and zero the motor
            try:
                self.motion.hold()
                self._log("✓ Motor hold enabled")
                self.motion.zero()
                self._log("✓ Motor zeroed")
            except Exception as e:
                self._log(f"⚠ Motor lock failed: {e}")
                messagebox.showerror("Error", f"Failed to lock motor: {e}")
                self.blade_locked = False  # Revert state
                self.lock_btn.config(text="LOCK BLADE")
                self._update_button_states()
                self._refocus_qr()
                return
            
            self.lock_btn.config(text="RELEASE BLADE")
        else:
            # Release: release the motor
            try:
                self.motion.release()
                self._log("✓ Motor released")
            except Exception as e:
                self._log(f"⚠ Motor release failed: {e}")
            
            self.lock_btn.config(text="LOCK BLADE")

        # Update instructions
        if not self.scan_ok:
            self.instructions_var.set("SCAN QR CODE ON BLADE")
        elif self.test_case_id is None:
            self.instructions_var.set("⚠ No test case - cannot upload. Scan different QR.")
        else:
            self.instructions_var.set(
                "Press START INSPECTION." if self.blade_locked else "Lock the blade, then press START INSPECTION."
            )

        self._update_button_states()
        self._refocus_qr()

    def _update_button_states(self):
        if self.is_running:
            self.lock_btn.config(state="disabled")
            self.start_btn.config(state="normal", style="Danger.TButton", text="STOP")
            return

        self.lock_btn.config(state="normal")

        # Only enable start if: scan ok, blade locked, AND has test case
        if self.scan_ok and self.blade_locked and self.test_case_id is not None:
            self.start_btn.config(state="normal", style="Primary.TButton", text="START INSPECTION")
        else:
            self.start_btn.config(state="disabled", style="Disabled.TButton", text="START INSPECTION")

    def _start_or_stop(self):
        if not self.is_running:
            if not (self.scan_ok and self.blade_locked and self.test_case_id is not None):
                return

            self.is_running = True
            self.stop_flag.clear()

            self.instructions_var.set("Inspection running...")
            self._update_button_states()

            self.run_thread = threading.Thread(target=self._run_inspection_loop, daemon=True)
            self.run_thread.start()
        else:
            self.stop_flag.set()
            try:
                self.motion.stop()
            except Exception:
                pass
            self.instructions_var.set("Stopping...")

    def _run_inspection_loop(self):
        """Run inspection using runner.py with temp file cleanup."""
        try:
            # Create observation via API
            api_config = api_config_from_env()
            client = ApiClient(api_config)
            
            # Determine scope
            scope = "incoming" if (self.cut_number is None or self.cut_number == 0) else "cut"
            
            # Create observation
            if scope == "cut":
                self._log(f"Creating observation for test case {self.test_case_id} (scope: {scope}, cut: {self.cut_number})...")
                obs_response = client.create_observation(self.test_case_id, cut_number=self.cut_number, scope=scope)
            else:
                self._log(f"Creating observation for test case {self.test_case_id} (scope: {scope})...")
                obs_response = client.create_observation(self.test_case_id, scope=scope)
            
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
            
            # Pause live preview during inspection
            self.preview_running = False
            
            # Configure inspection run
            config = RunConfig(
                teeth=self.teeth_count,
                captures=self.teeth_count,
                outdir=tempfile.gettempdir(),  # Use system temp directory
                done_timeout_s=15.0,
                make_run_subfolder=False,  # Don't create subfolders in temp
                observation_id=observation_id,
                api_config=api_config,
                cleanup_temp_files=True  # Delete files after upload
            )

            self._log("=" * 60)
            self._log(f"Starting inspection: {self.teeth_count} captures")
            self._log("=" * 60)

            # Run inspection
            result_dir = run_inspection(
                cfg=config,
                motion=self.motion,
                camera=self.camera,
                stop_flag=self.stop_flag,
                on_event=self._log,
                on_image_captured=self._display_captured_image
            )
            
            self._log("=" * 60)
            self._log(f"✓ Inspection complete!")
            self._log("=" * 60)
            
        except Exception as e:
            self._log(f"✗ Inspection failed: {e}")
            
            def show_error():
                messagebox.showerror("Inspection Error", f"Failed: {e}")
            
            self.after(0, show_error)
        finally:
            def done():
                self.is_running = False
                # Resume live preview
                if self.camera.is_open:
                    self.preview_running = True
                    self._update_preview()
                
                # Update instructions
                if not self.scan_ok:
                    self.instructions_var.set("SCAN QR CODE ON BLADE")
                elif self.test_case_id is None:
                    self.instructions_var.set("⚠ No test case - cannot upload. Scan different QR.")
                elif not self.blade_locked:
                    self.instructions_var.set("Lock the blade, then press START INSPECTION.")
                else:
                    self.instructions_var.set("Press START INSPECTION.")
                
                self._update_button_states()
                self._refocus_qr()

            self.after(0, done)

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
                self._last_photo = photo  # Keep reference
            except Exception as e:
                self._log(f"Failed to display image: {e}")
        
        # Schedule update on main thread
        self.after(0, update)

    # -------------------------
    # Close
    # -------------------------
    def _on_close(self):
        if self.is_running:
            if not messagebox.askyesno("Confirm Exit", "Inspection is running. Stop and exit?"):
                return
            self.stop_flag.set()

        self.preview_running = False

        if self._motor_retry_job is not None:
            try:
                self.after_cancel(self._motor_retry_job)
            except Exception:
                pass
            self._motor_retry_job = None

        try:
            self.motion.close()
        except Exception:
            pass

        try:
            self.camera.close()
        except Exception:
            pass

        self.destroy()


def main():
    motion = MotionController(cfg=MotionConfig(port=MOTOR_PORT))
    camera = USBCCamera(device_index=CAMERA_INDEX)

    app = InspectionGUI(motion=motion, camera=camera)
    app.mainloop()


if __name__ == "__main__":
    main()
