"""Domain data structures for the voice-agent pipeline.

Mirrors the FlowSight prototype's fake-data structs so the real extractor can be
checked against a known, hand-written codebase.
"""
from dataclasses import dataclass


@dataclass
class AudioChunk:
    pcm: bytes
    sample_rate: int
    frame_ms: int


@dataclass
class Transcript:
    text: str
    is_final: bool
    lang: str


@dataclass
class LLMMessage:
    role: str
    content: str
    context: list


@dataclass
class TTSAudio:
    pcm: bytes
    sample_rate: int
    duration: float
