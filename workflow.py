# workflow.py
"""
Inspection workflow orchestration layer.

Combines runner.py (inspection engine) + api_client.py (API client) for production use.
This is the ONLY module that imports both - it acts as the "glue" layer.
"""
from __future__ import annotations

import os
import tempfile
import threading
from typing import Callable, Optional

from runner import run_inspection, RunConfig
from api_client import ApiClient, api_config_from_env


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

    def api_step(msg: str):
        """Helper to update API progress."""
        nonlocal current_step
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
                
                # Update success counter
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
                # Update failure counter
                failed_count += 1
                had_failure = True
                if on_event:
                    on_event(f"⚠ Upload failed for tooth_{tooth_number}: {e}")
            
            # Update progress
            msg = f"Uploaded {uploaded_count} / {teeth_total} teeth"
            if failed_count:
                msg += f"  ({failed_count} failed)"
            api_step(msg)
        
        # Start upload in background thread
        threading.Thread(target=upload_worker, daemon=True).start()
    
    # Step 3: Configure inspection run
    config = RunConfig(
        teeth=teeth_count,
        captures=teeth_count,
        outdir=tempfile.gettempdir(),  # Use temp directory
        done_timeout_s=15.0,
        make_run_subfolder=False,
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
