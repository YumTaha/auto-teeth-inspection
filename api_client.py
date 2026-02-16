# api_client.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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

    def create_observation(self, test_case_id: int, cut_number: int, scope: str = "cut") -> Dict[str, Any]:
        """Create an observation for a test case.
        
        Args:
            test_case_id: The test case ID from active_test_case
            cut_number: The cut number from active_test_case.total_cuts
            scope: Observation scope - "cut" for normal inspections, "incoming" for initial inspection (cut_number=0)
            
        Returns:
            Response containing observation id
        """
        url = f"{self.cfg.base_url.rstrip('/')}/test-cases/{test_case_id}/observations"
        payload = {
            "observation_type_id": 1,
            "scope": scope,
            "cut_number": cut_number,
            # observation_value omitted - will attach pictures instead
        }
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        
        print(f"[API] POST {url}")
        print(f"[API] Headers: {headers}")
        print(f"[API] Payload: {payload}")
        
        r = requests.post(url, json=payload, headers=headers, timeout=10, verify=False)
        
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
