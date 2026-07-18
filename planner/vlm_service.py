"""
Warehouse AGV - VLM Service

Wraps MoondreamV2 running via Ollama for image understanding.
"""

import base64
from typing import Optional

import requests


OLLAMA_BASE_URL = "http://localhost:11434"
VLM_MODEL = "moondream"  # MoondreamV2 in Ollama


class VLMService:
    """Vision Language Model service using MoondreamV2 via Ollama."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = VLM_MODEL):
        self.base_url = base_url
        self.model = model
        self._ready = False
        self._check_model()

    def _check_model(self):
        """Verify the model is available in Ollama."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m["name"].split(":")[0] for m in models]
                if self.model in model_names:
                    self._ready = True
                    print(f"[VLM] Model '{self.model}' is available")
                else:
                    print(f"[VLM] WARNING: Model '{self.model}' not found in Ollama")
                    print(f"  Available: {model_names}")
                    print(f"  Run: ollama pull {self.model}")
            else:
                print(f"[VLM] WARNING: Ollama not responding")
        except requests.exceptions.ConnectionError:
            print(f"[VLM] WARNING: Cannot connect to Ollama at {self.base_url}")
            print("  Make sure Ollama is running: ollama serve")

    def is_ready(self) -> bool:
        return self._ready

    def describe(self, image_bytes: bytes, prompt: str) -> Optional[str]:
        """
        Get a description of an image from the VLM.
        
        Args:
            image_bytes: JPEG encoded image
            prompt: Text prompt for the VLM
            
        Returns:
            Description string or None on failure
        """
        if not self._ready:
            return None

        image_b64 = base64.b64encode(image_bytes).decode('utf-8')

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "options": {
                "temperature": 0.3,  # Low temperature for factual descriptions
                "num_predict": 200,  # Keep descriptions concise
            }
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=30
            )
            if resp.status_code == 200:
                result = resp.json()
                return result.get("response", "").strip()
            else:
                print(f"[VLM] Error: {resp.status_code} - {resp.text[:100]}")
                return None

        except requests.exceptions.Timeout:
            print("[VLM] Timeout - model may be loading")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[VLM] Request error: {e}")
            return None
