# api_client.py
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import requests
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class DuplicateObservationError(Exception):
    """Raised when an observation for the same cut already exists (duplicate unique constraint)."""
    pass


@dataclass
class ApiConfig:
    base_url: str  # e.g. "http://eng-ubuntu.mkmorse.local/api"


class ApiClient:
    def __init__(self, cfg: ApiConfig):
        self.cfg = cfg

    def _headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
        }

    def get_sample_context(self, identifier: str) -> Dict[str, Any]:
        # Email: GET /samples/identifier/{identifier}/context
        url = f"{self.cfg.base_url.rstrip('/')}/samples/identifier/{identifier}/context"
        headers = self._headers()
        
        print(f"[API] GET {url}")
        print(f"[API] Headers: {headers}")
        
        r = requests.get(url, headers=headers, timeout=10, verify=False)
        
        print(f"[API] Response Status: {r.status_code}")
        print(f"[API] Response Headers: {dict(r.headers)}")
        print(f"[API] Response Content: {r.text[:500]}")
        
        r.raise_for_status()
        return r.json()

    def create_observation(self, test_case_id: int, cut_number: int = None, scope: str = "cut") -> Dict[str, Any]:
        """Create an observation for a test case.
        
        Args:
            test_case_id: The test case ID from active_test_case
            cut_number: The cut number (only included when scope="cut")
            scope: Observation scope - "cut" for normal inspections, "incoming" for initial inspection
            
        Returns:
            Response containing observation id
        """
        url = f"{self.cfg.base_url.rstrip('/')}/test-cases/{test_case_id}/observations"
        payload = {
            "observation_type_id": 1,
            "scope": scope,
        }
        
        # Only include cut_number for cut-scoped observations
        if scope == "cut" and cut_number is not None:
            payload["cut_number"] = cut_number
        
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        
        print(f"[API] POST {url}")
        print(f"[API] Headers: {headers}")
        print(f"[API] Payload: {payload}")
        
        r = requests.post(url, json=payload, headers=headers, timeout=10, verify=False)
        
        # Friendly error for "duplicate observation" (unique constraint)
        if r.status_code == 400:
            body = (r.text or "").lower()
            if "idx_observations_cut_unique" in body or "sqlstate 23505" in body or "duplicate key value" in body:
                raise DuplicateObservationError(
                    "This inspection already exists for this cut (duplicate). "
                    "That observation already has images, so the system can’t create another one."
                )

        print(f"[API] Response Status: {r.status_code}")
        print(f"[API] Response Headers: {dict(r.headers)}")
        print(f"[API] Response Content Length: {len(r.content)} bytes")
        print(f"[API] Response Text: {r.text[:1000]}")
        
        r.raise_for_status()
        
        # Check if response has content
        if not r.content:
            raise ValueError(f"API returned empty response. Status: {r.status_code}, Headers: {dict(r.headers)}")
        
        # Get response content
        try:
            response_data = r.json()
            print(f"[API] Parsed JSON: {response_data}")
            if response_data is None:
                raise ValueError(f"JSON parsing returned None. Status: {r.status_code}, Content: {r.text[:500]}")
            return response_data
        except Exception as e:
            raise ValueError(f"Failed to parse JSON response. Status: {r.status_code}, Content: {r.text[:500]}") from e

    def upload_attachment(self, observation_id: int, file_path: str, tag: Optional[int] = None) -> Dict[str, Any]:
        """Upload an image attachment to an observation.
        
        Args:
            observation_id: The observation ID from create_observation response
            file_path: Path to the image file
            tag: Tooth number to tag the image with
            
        Returns:
            Response containing attachment metadata
        """
        url = f"{self.cfg.base_url.rstrip('/')}/observations/{observation_id}/upload"
        
        print(f"[API] POST {url}")
        print(f"[API] File: {file_path}")
        print(f"[API] Tag: {tag}")
        
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {}
            if tag is not None:
                data['tag'] = str(tag)
            
            # Don't send Accept: application/json header for multipart uploads
            headers = {}  # Let requests set Content-Type automatically
            r = requests.post(url, files=files, data=data, headers=headers, timeout=30, verify=False)
            
            print(f"[API] Response Status: {r.status_code}")
            print(f"[API] Response Headers: {dict(r.headers)}")
            print(f"[API] Response Text: {r.text[:500]}")
            
            r.raise_for_status()
            return r.json()


def extract_teeth_from_context(ctx: Dict[str, Any]) -> int:
    # Email: sample.design.attribute_values["Number of Teeth"]
    try:
        teeth = ctx["sample"]["design"]["attribute_values"]["Number of Teeth"]
    except KeyError as e:
        raise KeyError(f"Missing expected key in context JSON: {e}") from e

    if not isinstance(teeth, (int, float)):
        raise ValueError(f"Number of Teeth is not numeric: {teeth!r}")
    teeth_i = int(teeth)
    if teeth_i <= 0:
        raise ValueError(f"Invalid teeth count: {teeth_i}")
    return teeth_i


def extract_test_case_id_from_context(ctx: Dict[str, Any]) -> Optional[int]:
    """Extract active test case ID from context.
    
    Returns None if no active test case.
    """
    try:
        active_test_case = ctx.get("active_test_case")
        if active_test_case is None:
            return None
        return active_test_case["id"]
    except (KeyError, TypeError):
        return None


def extract_cut_number_from_context(ctx: Dict[str, Any]) -> Optional[int]:
    """Extract cut number (total_cuts) from active test case.
    
    Returns None if no active test case.
    """
    try:
        active_test_case = ctx.get("active_test_case")
        if active_test_case is None:
            return None
        return active_test_case["total_cuts"]
    except (KeyError, TypeError):
        return None


def api_config_from_env() -> ApiConfig:
    """
    Reads config from env:
      MKMORSE_API_BASE_URL  (default: https://eng-ubuntu.mkmorse.local/api)
    """
    base_url = os.getenv("MKMORSE_API_BASE_URL", "https://eng-ubuntu.mkmorse.local/api")
    return ApiConfig(base_url=base_url)


def run_inspection_workflow(
    test_case_id: int,
    cut_number: Optional[int],
    teeth_count: int,
    motion,
    camera,
    stop_flag,
    on_event: Optional[Callable[[str], None]] = None,
    on_image_captured: Optional[Callable[[str], None]] = None,
    on_api_progress: Optional[Callable[[int, int, str, bool], None]] = None,  # (current, total, msg, had_failure)
) -> str:
    """
    Complete inspection workflow with API integration.
    
    Handles:
    - Observation creation
    - Scope determination
    - Response validation
    - Inspection execution with temp file cleanup
    
    Args:
        test_case_id: Test case ID from API context
        cut_number: Cut number (None or 0 for incoming inspection)
        teeth_count: Number of teeth to capture
        motion: Motion controller instance
        camera: Camera instance
        stop_flag: Threading event for stopping inspection
        on_event: Optional callback for logging events
        on_image_captured: Optional callback for displaying captured images
    
    Returns:
        Result directory path (temp dir)
    """
    from runner import run_inspection, RunConfig
    
    # Get API configuration
    api_config = api_config_from_env()
    client = ApiClient(api_config)
    
    # Determine scope
    scope = "incoming" if (cut_number is None or cut_number == 0) else "cut"
    
    teeth_total = int(teeth_count)
    total_steps = 1 + int(teeth_total)  # 1 for observation + N uploads
    current_step = 0
    had_failure = False
    uploaded_count = 0
    failed_count = 0

    def api_step(msg: str):
        nonlocal current_step
        current_step += 1
        if on_api_progress:
            on_api_progress(current_step, total_steps, msg, had_failure)
            
    # Create observation
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
    
    # Configure inspection run with temp file cleanup
    config = RunConfig(
        teeth=teeth_count,
        captures=teeth_count,
        outdir=tempfile.gettempdir(),
        done_timeout_s=15.0,
        make_run_subfolder=False,
        observation_id=observation_id,
        api_config=api_config,
        cleanup_temp_files=True
    )
    
    if on_event:
        on_event("=" * 60)
        on_event(f"Starting inspection: {teeth_count} captures")
        on_event("=" * 60)
    
    # Run inspection
    def upload_result_cb(tooth_number: int, ok: bool, err: Optional[str]):
        nonlocal had_failure, uploaded_count, failed_count

        if ok:
            uploaded_count += 1
        else:
            failed_count += 1
            had_failure = True

        msg = f"Uploaded {uploaded_count} / {teeth_total} teeth"
        if failed_count:
            msg += f"  ({failed_count} failed)"

        api_step(msg)

    result_dir = run_inspection(
        cfg=config,
        motion=motion,
        camera=camera,
        stop_flag=stop_flag,
        on_event=on_event,
        on_image_captured=on_image_captured,
        on_upload_result=upload_result_cb,
    )

    
    if on_event:
        on_event("=" * 60)
        on_event(f"✓ Inspection complete!")
        on_event("=" * 60)
    
    return result_dir
