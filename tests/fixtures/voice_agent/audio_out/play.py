"""Audio playback: TTSAudio -> void."""


class Player:
    def __init__(self):
        self.queue = []

    def play(self, audio) -> None:
        """Enqueue an audio chunk for non-blocking playback."""
        self.queue.append(audio)
