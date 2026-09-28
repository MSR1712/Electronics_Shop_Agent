"""
Shared Deepgram (STT) + ElevenLabs (TTS) engine used by both
interfaces/voice_app.py (local mic/speaker) and api/routers/voice.py
(browser WebSocket bridge). Replaces the previous Gemini Live (native
audio) engine.

Gemini Live did turn-taking, VAD, and barge-in for free as part of one
audio-to-audio model. Deepgram and ElevenLabs are separate STT/TTS
services, so that behavior is built here instead:
  - `DeepgramTranscriber` keeps one streaming connection open for the
    whole session. Deepgram's own endpointing (`endpointing` +
    `utterance_end_ms`) decides when the customer has finished a turn —
    a finalized utterance is pushed onto `next_utterance()`.
  - `vad_events=True` makes Deepgram also emit a "speech started" event
    the instant it detects the customer talking, independent of
    endpointing. Callers pass an `on_speech_started` callback and treat
    it as a barge-in signal when the assistant's own reply is currently
    playing (Deepgram has no idea what the speaker is doing — the
    caller, which owns playback, is the only place that distinction can
    be made).
  - `ElevenLabsSpeaker` streams synthesized audio as raw PCM16 mono at
    OUTPUT_SAMPLE_RATE (`output_format="pcm_24000"`), matching this
    app's existing fixed playback rate exactly — no resampling needed
    anywhere in voice_app.py or the browser bridge.
"""

import asyncio
import inspect
from collections.abc import AsyncIterator, Callable

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from elevenlabs.client import AsyncElevenLabs

from config import settings

# Deepgram's streaming STT requires 16-bit PCM mono; ElevenLabs' pcm_24000
# output format is 16-bit PCM mono at 24kHz. Neither is a tunable knob —
# fixed by each API.
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000


class DeepgramTranscriber:
    """One long-lived Deepgram streaming connection per `async with` block.
    Feed mic audio in continuously via `send_audio()`; consume finalized
    customer utterances one at a time via `next_utterance()`."""

    def __init__(self, on_speech_started: Callable[[], object] | None = None):
        # `on_speech_started` may be a plain sync callback or an async one
        # (the WebSocket bridge needs to await a websocket.send() from it,
        # to signal "interrupted" the instant barge-in is detected rather
        # than waiting for the TTS loop to next check a flag) - `_on_message`
        # below awaits it either way.
        self._client = AsyncDeepgramClient(api_key=settings.deepgram_api_key)
        self._on_speech_started = on_speech_started
        self._connect_cm = None
        self._connection = None
        self._listen_task: asyncio.Task | None = None
        self._utterances: asyncio.Queue[str] = asyncio.Queue()
        self._partial: list[str] = []

    async def __aenter__(self) -> "DeepgramTranscriber":
        self._connect_cm = self._client.listen.v1.connect(
            model=settings.deepgram_model,
            language="en",
            encoding="linear16",
            sample_rate=INPUT_SAMPLE_RATE,
            channels=1,
            smart_format=True,
            interim_results=True,
            vad_events=True,
            # Short endpointing so a normal pause reads as "done talking"
            # quickly; utterance_end_ms is the backstop for when Deepgram
            # never marks a final result speech_final on its own (e.g. the
            # last word's confidence keeps it provisional).
            endpointing=300,
            utterance_end_ms=1000,
        )
        self._connection = await self._connect_cm.__aenter__()
        self._connection.on(EventType.MESSAGE, self._on_message)
        self._listen_task = asyncio.create_task(self._connection.start_listening())
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._listen_task is not None:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._connect_cm is not None:
            try:
                await self._connect_cm.__aexit__(*exc_info)
            except Exception:
                pass

    async def _on_message(self, msg) -> None:
        msg_type = getattr(msg, "type", None)
        if msg_type == "SpeechStarted":
            if self._on_speech_started is not None:
                result = self._on_speech_started()
                if inspect.isawaitable(result):
                    await result
            return
        if msg_type != "Results":
            return

        alt = msg.channel.alternatives[0]
        if msg.is_final and alt.transcript:
            self._partial.append(alt.transcript)
        if msg.speech_final:
            text = " ".join(self._partial).strip()
            self._partial.clear()
            if text:
                self._utterances.put_nowait(text)

    async def send_audio(self, chunk: bytes) -> None:
        if self._connection is not None:
            await self._connection.send_media(chunk)

    async def next_utterance(self) -> str:
        """Blocks until Deepgram finalizes the next customer turn."""
        return await self._utterances.get()


class ElevenLabsSpeaker:
    """Thin wrapper over ElevenLabs' streaming TTS. One `synthesize()` call
    per assistant reply — no persistent connection to manage, unlike STT."""

    def __init__(self):
        self._client = AsyncElevenLabs(api_key=settings.elevenlabs_api_key)

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        async for chunk in self._client.text_to_speech.stream(
            voice_id=settings.elevenlabs_voice_id,
            text=text,
            model_id=settings.elevenlabs_model_id,
            output_format="pcm_24000",
        ):
            yield chunk
