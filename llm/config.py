"""
Configuration for SmartTap LLM settings
"""

import os
from pathlib import Path

# LLM Configuration
DEFAULT_MODEL = "gemma3:latest"
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

def get_model_name():
    """Get the current LLM model from environment or use default"""
    return os.getenv("SMARTTAP_MODEL", DEFAULT_MODEL)

def set_model_name(model_name):
    """Set the LLM model for the current session"""
    os.environ["SMARTTAP_MODEL"] = model_name

# Supported models for evaluation (examples - install with ollama pull)
SUPPORTED_MODELS = [
    "gemma3:latest",
    "llama3.2:latest", 
    "gemma2:2b",
    "llama3.2:3b",
    "qwen2.5:3b",
    "phi3:mini",
    "mistral:7b",
    "llama3.1:8b",
]

# Model display names for reports
MODEL_DISPLAY_NAMES = {
    "gemma3:latest": "Gemma 3 (latest)",
    "llama3.2:latest": "Llama 3.2 (latest)",
    "gemma2:2b": "Gemma 2 (2B)",
    "llama3.2:3b": "Llama 3.2 (3B)",
    "qwen2.5:3b": "Qwen 2.5 (3B)",
    "phi3:mini": "Phi-3 Mini (3.8B)",
    "mistral:7b": "Mistral (7B)",
    "llama3.1:8b": "Llama 3.1 (8B)",
}

def get_model_display_name(model_name):
    """Get human-readable model name"""
    return MODEL_DISPLAY_NAMES.get(model_name, model_name)

def get_installed_models():
    """Get list of installed ollama models"""
    import subprocess
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')[1:]  # Skip header
            models = []
            for line in lines:
                if line.strip():
                    name = line.split()[0]  # First column is NAME
                    models.append(name)
            return models
        return []
    except Exception:
        return []
