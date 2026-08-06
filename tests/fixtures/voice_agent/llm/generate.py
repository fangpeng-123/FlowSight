"""LLM dialogue generation: Transcript -> LLMMessage."""
import requests

from voice_agent.models import LLMMessage, Transcript


class LLMClient:
    def __init__(self, base_url: str = "https://api.example.com"):
        self.base_url = base_url

    def generate(self, transcript: Transcript) -> LLMMessage:
        """Call the model endpoint and return an LLMMessage reply."""
        resp = requests.post(self.base_url + "/chat", json={"text": transcript.text})
        data = resp.json()
        return LLMMessage(role="assistant", content=data["text"], context=[])
