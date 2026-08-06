"""Microphone capture: produce AudioChunk frames."""
from voice_agent.models import AudioChunk


def receive_chunk(frame: bytes) -> AudioChunk:
    """Receive one microphone frame, wrap it as an AudioChunk."""
    return AudioChunk(pcm=frame, sample_rate=16000, frame_ms=20)
