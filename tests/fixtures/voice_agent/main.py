"""Entry point: wire the voice-agent pipeline end to end.

run() orchestrates the full chain:
  receive_chunk -> VADDetector.detect -> is_utterance_end
                -> transcribe -> LLMClient.generate -> synthesize -> Player.play
"""
from voice_agent.audio_in.stream import receive_chunk
from voice_agent.audio_in.vad import VADDetector, is_utterance_end
from voice_agent.asr.transcribe import transcribe
from voice_agent.llm.generate import LLMClient
from voice_agent.tts.synthesize import synthesize
from voice_agent.audio_out.play import Player


def run(frame: bytes) -> None:
    """Run one utterance through the pipeline."""
    chunk = receive_chunk(frame)
    vad = VADDetector()
    is_speech = vad.detect(chunk)
    if is_utterance_end(is_speech, chunk):
        transcript = transcribe([chunk])
        client = LLMClient()
        msg = client.generate(transcript)
        audio = synthesize(msg)
        player = Player()
        player.play(audio)
