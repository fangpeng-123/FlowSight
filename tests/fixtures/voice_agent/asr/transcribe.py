"""Streaming ASR: AudioChunk[] -> Transcript."""
from voice_agent.models import Transcript


def transcribe(chunks) -> Transcript:
    """Transcribe a sequence of audio chunks into a Transcript."""
    text = "".join(chr(b % 26 + 97) for b in b"".join(c.pcm for c in chunks))
    return Transcript(text=text, is_final=True, lang="zh")
