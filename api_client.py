# api_client.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict

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
        # Email: GET /samples/identifier/{identifier}/context :contentReference[oaicite:1]{index=1}
        url = f"{self.cfg.base_url.rstrip('/')}/samples/identifier/{identifier}/context"
        r = requests.get(url, headers=self._headers(), timeout=10, verify=False)
        r.raise_for_status()
        return r.json()


def extract_teeth_from_context(ctx: Dict[str, Any]) -> int:
    # Email: sample.design.attribute_values["Number of Teeth"] :contentReference[oaicite:2]{index=2}
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


def api_config_from_env() -> ApiConfig:
    """
    Reads config from env:
      MKMORSE_API_BASE_URL  (default: http://eng-ubuntu.mkmorse.local/api)
    """
    base_url = os.getenv("MKMORSE_API_BASE_URL", "http://eng-ubuntu.mkmorse.local/api")
    return ApiConfig(base_url=base_url)
