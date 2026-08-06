"""Voice-activity detection and utterance endpointing."""


class VADDetector:
    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    def detect(self, chunk) -> bool:
        """Return True if the chunk contains speech."""
        return len(chunk.pcm) > 0


def is_utterance_end(is_speech: bool, chunk) -> bool:
    """Return True if the utterance has ended (trailing silence)."""
    return not is_speech
