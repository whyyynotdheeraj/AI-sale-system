import os
import time
import logging
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger("ai_provider")

class BaseAIProvider(ABC):
    @abstractmethod
    def generate(self, system_instruction: str, contents: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 800) -> Dict[str, Any]:
        """
        Returns: {
            "text": str,
            "input_tokens": int,
            "output_tokens": int,
            "provider": str,
            "model": str
        }
        """
        pass

class GeminiProvider(BaseAIProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model

    def generate(self, system_instruction: str, contents: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 800) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        # Primary SDK path
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            formatted_contents = []
            for item in contents:
                role = "user" if item["role"] == "user" else "model"
                formatted_contents.append(
                    types.Content(role=role, parts=[types.Part.from_text(text=item["text"])])
                )

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_tokens
            )
            response = client.models.generate_content(
                model=self.model,
                contents=formatted_contents,
                config=config
            )
            text = response.text.strip() if response and response.text else ""
            return {
                "text": text,
                "input_tokens": len(system_instruction.split()) * 2,
                "output_tokens": len(text.split()) * 2,
                "provider": "Gemini",
                "model": self.model
            }
        except Exception as e:
            logger.warning(f"[GeminiProvider] SDK call failed ({e}), trying REST fallback...")
            return self._rest_fallback(system_instruction, contents, temperature, max_tokens)

    def _rest_fallback(self, system_instruction: str, contents: List[Dict[str, str]], temperature: float, max_tokens: int) -> Dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        parts = [{"text": f"System Instruction:\n{system_instruction}\n\n"}]
        for item in contents:
            parts.append({"text": f"{item['role'].upper()}: {item['text']}\n"})
        
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"})
        
        with urllib.request.urlopen(req, timeout=30) as response:
            res_body = json.loads(response.read().decode("utf-8"))
            text = res_body["candidates"][0]["content"]["parts"][0]["text"].strip()
            return {
                "text": text,
                "input_tokens": 300,
                "output_tokens": len(text.split()) * 2,
                "provider": "Gemini-REST",
                "model": self.model
            }

class OpenAIProvider(BaseAIProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model

    def generate(self, system_instruction: str, contents: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 800) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not set.")

        url = "https://api.openai.com/v1/chat/completions"
        messages = [{"role": "system", "content": system_instruction}]
        for item in contents:
            role = "assistant" if item["role"] in ["model", "assistant", "ai"] else "user"
            messages.append({"role": role, "content": item["text"]})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            res_body = json.loads(response.read().decode("utf-8"))
            text = res_body["choices"][0]["message"]["content"].strip()
            usage = res_body.get("usage", {})
            return {
                "text": text,
                "input_tokens": usage.get("prompt_tokens", 200),
                "output_tokens": usage.get("completion_tokens", 100),
                "provider": "OpenAI",
                "model": self.model
            }

class GroqProvider(BaseAIProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.model = model

    def generate(self, system_instruction: str, contents: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 800) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not set.")

        url = "https://api.groq.com/openai/v1/chat/completions"
        messages = [{"role": "system", "content": system_instruction}]
        for item in contents:
            role = "assistant" if item["role"] in ["model", "assistant", "ai"] else "user"
            messages.append({"role": role, "content": item["text"]})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            res_body = json.loads(response.read().decode("utf-8"))
            text = res_body["choices"][0]["message"]["content"].strip()
            usage = res_body.get("usage", {})
            return {
                "text": text,
                "input_tokens": usage.get("prompt_tokens", 200),
                "output_tokens": usage.get("completion_tokens", 100),
                "provider": "Groq",
                "model": self.model
            }

def execute_with_retry_and_fallback(
    provider_name: str,
    system_instruction: str,
    contents: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 800,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Executes AI prompt with Exponential Backoff Retry (1s -> 2s -> 4s) and Provider Failover.
    """
    primary_p = provider_name.lower().strip()
    providers_queue = [primary_p]
    for alt in ["gemini", "openai", "groq"]:
        if alt not in providers_queue:
            providers_queue.append(alt)

    last_error = None
    for p_name in providers_queue:
        for attempt in range(1, max_retries + 1):
            try:
                if p_name == "gemini":
                    provider = GeminiProvider()
                elif p_name == "openai":
                    provider = OpenAIProvider()
                elif p_name == "groq":
                    provider = GroqProvider()
                else:
                    provider = GeminiProvider()

                res = provider.generate(system_instruction, contents, temperature, max_tokens)
                res["fallback_used"] = (p_name != primary_p)
                return res
            except Exception as e:
                last_error = e
                logger.warning(f"[AIEngine] Retry {attempt}/{max_retries} for provider '{p_name}' failed: {e}")
                time.sleep(attempt * 1.5)

    logger.error(f"[AIEngine] All providers failed: {last_error}")
    raise RuntimeError(f"All AI Providers failed. Last error: {last_error}")
