"""
Warehouse AGV - LLM Service

Wraps Phi-3 Mini running via Ollama for navigation planning.
"""

from typing import Optional

import requests

from prompts import SYSTEM_PROMPT


OLLAMA_BASE_URL = "http://localhost:11434"
LLM_MODEL = "phi3:mini"  # Phi-3 Mini 3.8B in Ollama


class LLMService:
    """LLM planning service using Phi-3 Mini via Ollama."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = LLM_MODEL):
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
                model_names = [m["name"] for m in models]
                # Check for exact match or prefix match
                found = any(self.model in name for name in model_names)
                if found:
                    self._ready = True
                    print(f"[LLM] Model '{self.model}' is available")
                else:
                    print(f"[LLM] WARNING: Model '{self.model}' not found in Ollama")
                    print(f"  Available: {model_names}")
                    print(f"  Run: ollama pull {self.model}")
            else:
                print(f"[LLM] WARNING: Ollama not responding")
        except requests.exceptions.ConnectionError:
            print(f"[LLM] WARNING: Cannot connect to Ollama at {self.base_url}")

    def is_ready(self) -> bool:
        return self._ready

    def plan(self, user_prompt: str) -> Optional[str]:
        """
        Get a navigation plan from the LLM.
        
        Args:
            user_prompt: The planning prompt with context
            
        Returns:
            LLM response text or None on failure
        """
        if not self._ready:
            return None

        payload = {
            "model": self.model,
            "prompt": user_prompt,
            "system": SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "temperature": 0.4,  # Moderate creativity for planning
                "num_predict": 500,  # Enough for a multi-step plan
                "top_p": 0.9,
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
                print(f"[LLM] Error: {resp.status_code} - {resp.text[:100]}")
                return None

        except requests.exceptions.Timeout:
            print("[LLM] Timeout - model may be loading")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[LLM] Request error: {e}")
            return None
