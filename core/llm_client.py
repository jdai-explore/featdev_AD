"""
Universal Provider-Agnostic LLM Client for Autonomous ADAS/AD Agents
Adheres strictly to the standard OpenAI-compatible API format (POST /v1/chat/completions).
Compatible with:
  - Local Ollama (auto-detects local models e.g. gemma4:12b, qwen3-vl:latest, gemma4:latest)
  - Google Gemini (via OpenAI compatibility endpoint)
  - OpenAI (GPT-4o, GPT-4-turbo)
  - Groq / Mistral / Together / vLLM / LM Studio / OpenRouter

Persistence & Precedence Order:
  1. Explicit constructor arguments (if supplied)
  2. Active process environment variables (LLM_API_KEY, LLM_MODEL, LLM_BASE_URL)
  3. Local configuration file: config/llm_active_config.json (remembers user selections across restarts)
  4. .env file in root
  5. Automatic local Ollama discovery: defaults to gemma4:12b (or qwen3-vl / gemma4:latest) if Ollama is running
  6. Deterministic offline simulation fallback (air-gapped CI/CD)
"""

import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config/llm_active_config.json"
ENV_FILE = ROOT / ".env"

PREFERRED_LOCAL_MODELS = [
    "gemma4:12b",
    "qwen3-vl:latest",
    "gemma4:latest"
]

class LLMClientError(Exception):
    """Raised when an LLM inference call fails."""
    pass

def load_persisted_config() -> Dict[str, Any]:
    """Reads persisted user model configuration if saved."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_persisted_config(model: str, base_url: str, api_key: str = "", provider: str = "custom") -> None:
    """Saves user-configured LLM selection so it persists across UI & application restarts."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "provider": provider
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

def detect_local_ollama() -> Optional[Dict[str, Any]]:
    """Probes local Ollama instance on http://127.0.0.1:11434 and checks available models."""
    ollama_url = "http://127.0.0.1:11434"
    try:
        req = urllib.request.Request(f"{ollama_url}/api/tags")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            installed_names = [m.get("name") for m in data.get("models", [])]

            # Match against preferred local models
            chosen_model = None
            for pref in PREFERRED_LOCAL_MODELS:
                if pref in installed_names:
                    chosen_model = pref
                    break
            if not chosen_model and installed_names:
                chosen_model = installed_names[0]

            if chosen_model:
                return {
                    "base_url": f"{ollama_url}/v1",
                    "model": chosen_model,
                    "available_models": installed_names,
                    "provider": "ollama"
                }
    except Exception:
        pass
    return None

def _read_env_file() -> Dict[str, str]:
    """Lightweight .env reader without third-party dependencies."""
    env_vars = {}
    if ENV_FILE.exists():
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip().strip("'\"")
        except Exception:
            pass
    return env_vars

class UniversalLLMClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        offline_fallback: bool = True
    ):
        persisted = load_persisted_config()
        file_env = _read_env_file()

        # 1. Resolve API Key
        self.api_key = (
            api_key
            or os.environ.get("LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or persisted.get("api_key")
            or file_env.get("LLM_API_KEY")
            or file_env.get("OPENAI_API_KEY")
            or file_env.get("GEMINI_API_KEY")
            or ""
        )

        # 2. Check for local Ollama auto-detection if no explicit key/endpoint given
        ollama_info = None
        has_explicit_remote_key = bool(self.api_key) and not self.api_key.lower().startswith("ollama")

        # 3. Resolve Base URL
        env_base = (
            os.environ.get("LLM_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or file_env.get("LLM_BASE_URL")
            or file_env.get("OPENAI_BASE_URL")
        )

        if base_url:
            self.base_url = base_url.rstrip("/")
        elif env_base:
            self.base_url = env_base.rstrip("/")
        elif persisted.get("base_url"):
            self.base_url = persisted["base_url"].rstrip("/")
        elif not has_explicit_remote_key:
            # Check local Ollama
            ollama_info = detect_local_ollama()
            if ollama_info:
                self.base_url = ollama_info["base_url"]
            elif os.environ.get("OLLAMA_HOST"):
                self.base_url = f"{os.environ.get('OLLAMA_HOST').rstrip('/')}/v1"
            elif os.environ.get("GEMINI_API_KEY") or self.api_key.startswith("AIza"):
                self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
            else:
                self.base_url = "https://api.openai.com/v1"
        elif os.environ.get("GEMINI_API_KEY") or self.api_key.startswith("AIza"):
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        else:
            self.base_url = "https://api.openai.com/v1"

        # 4. Resolve Model Name
        _model_env = os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL") or file_env.get("LLM_MODEL")
        if model:
            self.model = model
        elif _model_env:
            self.model = _model_env
        elif persisted.get("model"):
            self.model = persisted["model"]
        elif ollama_info:
            self.model = ollama_info["model"]
        elif "11434" in self.base_url or "ollama" in self.base_url:
            self.model = "gemma4:12b"
        elif "generativelanguage.googleapis.com" in self.base_url:
            self.model = "gemini-2.5-pro"
        else:
            # If no key, default to local gemma4:12b preference
            self.model = "gemma4:12b" if not self.api_key else "gpt-4o"

        self.offline_fallback = offline_fallback

    def configure_and_persist(self, model: str, base_url: Optional[str] = None, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Dynamically updates model configuration and persists to config/llm_active_config.json.
        """
        self.model = model
        if base_url:
            self.base_url = base_url.rstrip("/")
        if api_key is not None:
            self.api_key = api_key

        provider = "ollama" if ("11434" in self.base_url or not self.api_key) else "cloud_api"
        save_persisted_config(
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            provider=provider
        )
        return {
            "status": "CONFIG_PERSISTED",
            "model": self.model,
            "base_url": self.base_url,
            "api_key_configured": bool(self.api_key),
            "provider": provider
        }

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        seed: int = 424242
    ) -> Dict[str, Any]:
        """
        Sends a standard chat completion request with optional tool definitions.
        Returns a dict matching the OpenAI chat completion response format:
        {
            "id": "...",
            "model": "...",
            "content": "...",
            "tool_calls": [ ... ] or None
        }
        """
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "seed": seed
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Check if we have credentials or should run in offline fallback
        is_local = "localhost" in self.base_url or "127.0.0.1" in self.base_url
        if not self.api_key and not is_local:
            if self.offline_fallback:
                return self._synthesize_offline_response(messages, tools)
            raise LLMClientError(
                "No API Key provided and offline fallback is disabled. "
                "Set LLM_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY."
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif is_local:
            headers["Authorization"] = "Bearer ollama"

        if "generativelanguage.googleapis.com" in self.base_url and self.api_key:
            headers["x-goog-api-key"] = self.api_key

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

        try:
            # Local models might take a moment to load weights into VRAM on first prompt
            timeout_val = 180 if is_local else 60
            with urllib.request.urlopen(req, timeout=timeout_val) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                choice = resp_data.get("choices", [{}])[0]
                message = choice.get("message", {})

                raw_content = message.get("content") or ""
                # Handle thinking/reasoning models (like gemma4 or DeepSeek R1) that put thought trace in reasoning field
                if not raw_content and message.get("reasoning"):
                    raw_content = message.get("reasoning")

                return {
                    "id": resp_data.get("id", "resp_live"),
                    "model": resp_data.get("model", self.model),
                    "content": raw_content,
                    "reasoning": message.get("reasoning"),
                    "tool_calls": message.get("tool_calls")
                }
        except Exception as e:
            if self.offline_fallback:
                return self._synthesize_offline_response(messages, tools)
            raise LLMClientError(f"HTTP call to {url} failed: {e}")

    def _synthesize_offline_response(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Deterministic offline simulation fallback for continuous integration,
        air-gapped systems, and local verification without cloud fees.
        """
        user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        
        # If tools are provided and user prompt mentions regulatory standards, trigger tool call
        if tools and any(kw in user_message.lower() for kw in ["unece", "r157", "r171", "regulation", "law", "standard"]):
            target_tool = next((t["function"]["name"] for t in tools if "regulation" in t["function"]["name"] or "fetch" in t["function"]["name"]), None)
            if target_tool:
                return {
                    "id": "mock_tool_call_001",
                    "model": f"{self.model}-offline-sim",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_unece_r157_01",
                            "type": "function",
                            "function": {
                                "name": target_tool,
                                "arguments": json.dumps({
                                    "query_or_url": "https://unece.org/transport/vehicle-regulations/wp29/un-regulations-141-160",
                                    "standard_id": "UN_R157"
                                })
                            }
                        }
                    ]
                }

        # Otherwise synthesize an engineering response
        return {
            "id": "mock_completion_001",
            "model": f"{self.model}-offline-sim",
            "content": f"[OFFLINE_SIMULATION: {self.model}] Processed instructions with zero-temperature determinism. Analysis complete.",
            "tool_calls": None
        }
