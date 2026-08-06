"""Text-to-speech: LLMMessage -> TTSAudio."""
from voice_agent.models import LLMMessage, TTSAudio


def synthesize(msg: LLMMessage) -> TTSAudio:
    """Synthesize speech audio from an LLM message."""
    return TTSAudio(pcm=msg.content.encode("utf-8"), sample_rate=24000, duration=0.0)
