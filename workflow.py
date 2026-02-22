# workflow.py
"""
Inspection workflow orchestration layer.

Combines runner.py (inspection engine) + api_client.py (API client) for production use.
This is the ONLY module that imports both - it acts as the "glue" layer.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from typing import Callable, Optional

from runner import run_inspection, RunConfig
from api_client import ApiClient, api_config_from_env


def cleanup_old_inspection_temp_dirs(
    prefix: str = "inspection_",
    max_age_hours: float = 24,
    on_event: Optional[Callable[[str], None]] = None
) -> int:
    """
    Clean up old inspection temp directories to prevent disk buildup.
    
    Scans the system temp directory for folders starting with `prefix` and deletes
    those older than `max_age_hours`. Includes safety checks to avoid deleting
    active inspections.
    
    Args:
        prefix: Directory name prefix to match (default: "inspection_")
        max_age_hours: Maximum age in hours before deletion (default: 24)
        on_event: Optional callback for logging events
    
    Returns:
        Number of directories successfully deleted
    
    Safety features:
        - Skips directories less than 5 minutes old (likely active)
        - Handles permission errors gracefully
        - Logs detailed information about deleted directories
    """
    try:
        temp_root = tempfile.gettempdir()
        now = time.time()
        max_age_seconds = max_age_hours * 3600
        min_age_seconds = 300  # 5 minutes safety window
        
        deleted_dirs = []
        skipped_active = []
        failed_dirs = []
        
        # Scan temp directory for matching folders
        for dirname in os.listdir(temp_root):
            if not dirname.startswith(prefix):
                continue
            
            full_path = os.path.join(temp_root, dirname)
            
            # Only process directories
            if not os.path.isdir(full_path):
                continue
            
            try:
                # Get directory modification time
                mtime = os.path.getmtime(full_path)
                age_seconds = now - mtime
                
                # Safety: Skip very recent directories (likely active inspections)
                if age_seconds < min_age_seconds:
                    skipped_active.append(dirname)
                    continue
                
                # Delete if older than threshold
                if age_seconds > max_age_seconds:
                    shutil.rmtree(full_path)
                    deleted_dirs.append(dirname)
                    
            except (OSError, PermissionError) as e:
                failed_dirs.append((dirname, str(e)))
        
        # Log results
        if on_event:
            if deleted_dirs:
                # Show first 3 deleted directories
                preview = deleted_dirs[:3]
                more = f" (+{len(deleted_dirs) - 3} more)" if len(deleted_dirs) > 3 else ""
                on_event(f"🧹 Deleted old temp dirs: {', '.join(preview)}{more}")
            
            if skipped_active:
                on_event(f"🔒 Skipped {len(skipped_active)} recent dirs (active inspections)")
            
            if failed_dirs:
                for dirname, error in failed_dirs[:2]:  # Show first 2 failures
                    on_event(f"⚠ Failed to delete {dirname}: {error}")
        
        return len(deleted_dirs)
        
    except (OSError, PermissionError) as e:
        if on_event:
            on_event(f"⚠ Temp cleanup failed: {e}")
        return 0


def run_inspection_with_api(
    test_case_id: int,
    cut_number: Optional[int],
    teeth_count: int,
    motion,
    camera,
    stop_flag,
    on_event: Optional[Callable[[str], None]] = None,
    on_image_captured: Optional[Callable[[str], None]] = None,
    on_api_progress: Optional[Callable[[int, int, str, bool], None]] = None,
) -> str:
    """
    Complete inspection workflow with API integration.
    
    This function orchestrates the entire process:
    1. Creates observation via API
    2. Runs physical inspection (motor + camera)
    3. Uploads images in background
    4. Deletes temp files after successful upload
    
    Args:
        test_case_id: Test case ID from API context
        cut_number: Cut number (None or 0 for incoming inspection)
        teeth_count: Number of teeth to capture
        motion: Motion controller instance
        camera: Camera instance
        stop_flag: Threading event for stopping inspection
        on_event: Optional callback for logging events
        on_image_captured: Optional callback for displaying captured images
        on_api_progress: Optional callback for API progress (current, total, msg, had_failure)
    
    Returns:
        Result directory path (temp dir where images were saved)
    """
    
    # Get API configuration
    api_config = api_config_from_env()
    client = ApiClient(api_config)
    
    # Determine scope
    scope = "incoming" if (cut_number is None or cut_number == 0) else "cut"
    
    # Progress tracking
    teeth_total = int(teeth_count)
    total_steps = 1 + teeth_total  # 1 for observation creation + N for uploads
    current_step = 0
    had_failure = False
    uploaded_count = 0
    failed_count = 0
    
    # Thread safety for counter updates from background upload threads
    progress_lock = threading.Lock()

    def api_step(msg: str):
        """Helper to update API progress."""
        nonlocal current_step
        with progress_lock:  # Thread-safe increment
            current_step += 1
            if on_api_progress:
                on_api_progress(current_step, total_steps, msg, had_failure)
    
    # Step 1: Create observation via API
    if on_event:
        on_event(f"Creating observation for test case {test_case_id} (scope: {scope})...")
    
    if scope == "cut":
        obs_response = client.create_observation(test_case_id, cut_number=cut_number, scope=scope)
    else:
        obs_response = client.create_observation(test_case_id, scope=scope)
    
    # Validate response
    if obs_response is None:
        raise ValueError("API returned None response")
    if not isinstance(obs_response, dict):
        raise ValueError(f"API returned unexpected type: {type(obs_response)}")
    
    observation_id = obs_response.get("id")
    if observation_id is None:
        raise ValueError(f"No 'id' in observation response: {obs_response}")
    
    api_step(f"Observation created (ID {observation_id})")

    if on_event:
        on_event(f"✓ Created observation ID: {observation_id}")
    
    # Step 2: Define upload callback for background uploads
    def handle_file_ready(filepath: str, tooth_number: int):
        """
        Called by runner when a file is ready.
        Uploads to API in background thread and deletes temp file after success.
        """
        nonlocal had_failure, uploaded_count, failed_count
        
        def upload_worker():
            """Background worker to upload image without blocking."""
            nonlocal had_failure, uploaded_count, failed_count
            
            try:
                # Upload to API
                client.upload_attachment(observation_id, filepath, tag=tooth_number)
                if on_event:
                    on_event(f"✓ Uploaded tooth_{tooth_number} to observation")
                
                # Update success counter (thread-safe)
                with progress_lock:
                    uploaded_count += 1
                
                # Delete temp file after successful upload
                try:
                    os.remove(filepath)
                    if on_event:
                        on_event(f"✓ Deleted temp file: tooth_{tooth_number}")
                except Exception as del_err:
                    if on_event:
                        on_event(f"⚠ Failed to delete temp file tooth_{tooth_number}: {del_err}")
                
            except Exception as e:
                # Update failure counter (thread-safe)
                with progress_lock:
                    failed_count += 1
                    had_failure = True
                if on_event:
                    on_event(f"⚠ Upload failed for tooth_{tooth_number}: {e}")
            
            # Update progress (thread-safe)
            with progress_lock:
                msg = f"Uploaded {uploaded_count} / {teeth_total} teeth"
                if failed_count:
                    msg += f"  ({failed_count} failed)"
            api_step(msg)
        
        # Start upload in background thread
        threading.Thread(target=upload_worker, daemon=True).start()
    
    # Step 3: Configure inspection run with unique temp directory
    # Use unique temp directory to prevent image overwrites on retries
    temp_dir = tempfile.mkdtemp(prefix="inspection_")
    
    config = RunConfig(
        teeth=teeth_count,
        captures=teeth_count,
        outdir=temp_dir,  # Unique temp directory per inspection
        done_timeout_s=15.0,
        make_run_subfolder=False,  # Already unique
    )
    
    if on_event:
        on_event("=" * 60)
        on_event(f"Starting inspection: {teeth_count} captures")
        on_event("=" * 60)
    
    # Step 4: Run inspection (runner calls handle_file_ready for each captured image)
    result_dir = run_inspection(
        cfg=config,
        motion=motion,
        camera=camera,
        stop_flag=stop_flag,
        on_event=on_event,
        on_image_captured=on_image_captured,
        on_file_ready=handle_file_ready,  # Upload callback injected here
    )
    
    if on_event:
        on_event("=" * 60)
        on_event("✓ Inspection complete!")
        on_event("=" * 60)
    
    return result_dir
