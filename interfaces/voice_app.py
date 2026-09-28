"""
Voice I/O layer: microphone <-> Deepgram (STT) + ElevenLabs (TTS) <-> speaker.

DESIGN CONSTRAINT (read this before changing anything here):
  Deepgram/ElevenLabs sit at the same I/O-only boundary Gemini Live used
  to. Every finalized customer utterance goes through
  handle_customer_message(text), which is the only thing that talks to
  the real LangGraph decision-maker (build_graph(), shared with
  chat_app.py) — the same bound customer_id/conversation_id, atomic
  confirm_order workflow, and ownership checks apply exactly as they do
  for text chat. This module never reasons about business logic itself;
  if the assistant needs a new capability, add it to a sub-agent in
  agents/, not here.

  Turn-taking/VAD/barge-in that Gemini Live used to provide natively is
  now built on top of Deepgram's streaming endpointing and speech-started
  events — see interfaces/voice_engine.py for the design.

AUTH NOTE: same demo caveat as chat_app.py - customer is selected from
seeded demo customers, not real authentication.

Requires local mic/speaker access (sounddevice), a Deepgram API key
(STT) and an ElevenLabs API key (TTS). Streams audio continuously rather
than recording in fixed turns.

Run with:
    python -m interfaces.voice_app
"""

import asyncio
import queue
import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import sounddevice as sd  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from config import settings  # noqa: E402
from db.models import Customer  # noqa: E402
from db.session import get_session, init_db  # noqa: E402
from graph import build_graph  # noqa: E402
from interfaces.text_utils import extract_text  # noqa: E402
from interfaces.voice_engine import (  # noqa: E402
    INPUT_SAMPLE_RATE,
    OUTPUT_SAMPLE_RATE,
    DeepgramTranscriber,
    ElevenLabsSpeaker,
)

# extract_text used to be duplicated here rather than imported from
# chat_app.py: chat_app.py is a Streamlit script, and importing it runs its
# module-level code as a side effect (builds a second, throwaway graph + DB
# connection, floods the console with "missing ScriptRunContext" warnings).
# interfaces/text_utils.py has no such side effects, so both chat_app.py and
# this module import the same function from there instead.

INPUT_BLOCK_SIZE = 1600  # 100ms of audio per mic callback


def _wasapi_device(kind: str):
    """Prefer the WASAPI host API's default device over sounddevice's
    system default (typically MME on Windows). MME's sample-rate conversion
    from this app's fixed 16kHz/24kHz PCM to the device's native rate
    (commonly 44.1kHz) is unreliable and produces sped-up, garbled audio -
    WASAPI shared mode uses Windows' own audio engine resampler instead.
    Falls back to None (sounddevice's default) on non-Windows or if no
    WASAPI host API is present."""
    try:
        wasapi = next(h for h in sd.query_hostapis() if h["name"] == "Windows WASAPI")
    except StopIteration:
        return None
    device = wasapi[f"default_{kind}_device"]
    return device if device >= 0 else None


def _wasapi_extra_settings(device):
    """WASAPI shared mode rejects any sample rate that doesn't exactly match
    the system mixer unless auto_convert is set - without it, opening this
    app's fixed-rate streams against a WASAPI device raises 'Invalid sample
    rate' (PaErrorCode -9997). Only meaningful (and only valid to pass) when
    the stream's device is actually a WASAPI one."""
    return sd.WasapiSettings(auto_convert=True) if device is not None else None


def choose_customer() -> str:
    with get_session() as session:
        customers = session.query(Customer).order_by(Customer.id).all()
    if not customers:
        raise RuntimeError("No demo customers found. Run `python -m scripts.seed_demo_data` first.")

    print("Demo login - choose a customer:")
    for i, c in enumerate(customers, start=1):
        print(f"  {i}. {c.name} ({c.id})")
    choice = input("Enter number: ").strip()
    try:
        idx = int(choice) - 1
        return customers[idx].id
    except (ValueError, IndexError):
        print("Invalid choice, defaulting to first customer.")
        return customers[0].id


def drain(q) -> None:
    while True:
        try:
            q.get_nowait()
        except (queue.Empty, asyncio.QueueEmpty):
            break


async def run_session(customer_id: str) -> None:
    app_graph = build_graph()
    thread_id = str(uuid.uuid4())
    print(f"Conversation ID: {thread_id}")

    async def handle_customer_message(text: str) -> str:
        """Routes one finalized customer utterance to the same shared
        LangGraph chat_app.py uses, the same way, with the same interrupt
        handling - this function is the entire boundary between voice I/O
        and the real decision-making logic."""
        config = {"configurable": {"thread_id": thread_id}}
        graph_input = {
            "messages": [HumanMessage(content=text)],
            "customer_id": customer_id,
            "conversation_id": thread_id,
        }
        try:
            # graph.invoke is sync (this project's SqliteSaver checkpointer
            # does not support async methods - graph.ainvoke raises
            # NotImplementedError against it) so it's run off the event
            # loop thread instead, matching how a blocking call would be
            # handled behind any async I/O layer.
            result = await asyncio.to_thread(app_graph.invoke, graph_input, config=config)
        except Exception as e:
            print(f"[error] graph invocation failed: {e}")
            return "Sorry, something went wrong on our end. Could you try again?"

        if "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            return payload.get("message", "You're being connected to a human agent.")

        last_ai = next(
            (m for m in reversed(result["messages"]) if isinstance(m, AIMessage)),
            None,
        )
        return extract_text(last_ai.content) if last_ai else "Sorry, I did not catch that."

    loop = asyncio.get_running_loop()
    audio_in_queue: asyncio.Queue[bytes] = asyncio.Queue()
    audio_out_queue: queue.Queue[bytes] = queue.Queue()

    # See interfaces/voice_engine.py: Deepgram's vad_events fire a
    # "speech started" event any time it detects the customer talking. It
    # only counts as a barge-in when the assistant's own reply is actually
    # playing right now, which is why on_speech_started checks `speaking`
    # before acting.
    speaking = asyncio.Event()
    barge_in = asyncio.Event()

    def mic_callback(indata, _frames, _time_info, _status) -> None:
        # Runs on PortAudio's own thread - hop into the event loop via
        # call_soon_threadsafe rather than touching the asyncio.Queue directly.
        loop.call_soon_threadsafe(audio_in_queue.put_nowait, bytes(indata))

    # Chunks arriving from ElevenLabs (via audio_out_queue) are not sized to
    # match one playback callback's frame count - a single queued chunk is
    # often much larger than `needed` below. This carries any excess from
    # one callback over to the next instead of discarding it.
    leftover = bytearray()

    def speaker_callback(outdata, _frames, _time_info, _status) -> None:
        # Also runs on PortAudio's thread. queue.Queue is already
        # thread-safe, so no call_soon_threadsafe is needed on this side -
        # only reading a plain queue.Queue.get_nowait(), never touching
        # the event loop.
        needed = len(outdata)
        buf = leftover[:needed]
        del leftover[:needed]
        while len(buf) < needed:
            try:
                buf.extend(audio_out_queue.get_nowait())
            except queue.Empty:
                break
        if len(buf) > needed:
            leftover.extend(buf[needed:])
            del buf[needed:]
        buf.extend(b"\x00" * (needed - len(buf)))  # pad with silence on underrun
        outdata[:] = bytes(buf)

    def on_speech_started() -> None:
        if speaking.is_set():
            barge_in.set()
            leftover.clear()
            drain(audio_out_queue)

    async def pump_mic(transcriber: DeepgramTranscriber) -> None:
        while True:
            chunk = await audio_in_queue.get()
            await transcriber.send_audio(chunk)

    async def speak(text: str, tts: ElevenLabsSpeaker) -> None:
        speaking.set()
        barge_in.clear()
        try:
            async for chunk in tts.synthesize(text):
                if barge_in.is_set():
                    break
                audio_out_queue.put_nowait(chunk)
        except Exception as e:
            print(f"[error] speech synthesis failed: {e}")
        finally:
            speaking.clear()

    async def conversation_loop(transcriber: DeepgramTranscriber, tts: ElevenLabsSpeaker) -> None:
        while True:
            text = await transcriber.next_utterance()
            print(f"You said: {text}")
            reply = await handle_customer_message(text)
            print(f"Assistant: {reply}")
            await speak(reply, tts)

    input_device = _wasapi_device("input")
    output_device = _wasapi_device("output")
    tts = ElevenLabsSpeaker()

    with sd.RawInputStream(
        samplerate=INPUT_SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=INPUT_BLOCK_SIZE,
        device=input_device,
        extra_settings=_wasapi_extra_settings(input_device),
        callback=mic_callback,
    ), sd.RawOutputStream(
        samplerate=OUTPUT_SAMPLE_RATE,
        device=output_device,
        extra_settings=_wasapi_extra_settings(output_device),
        channels=1,
        dtype="int16",
        callback=speaker_callback,
    ):
        # Deepgram's streaming connection is a long-lived websocket over the
        # open internet - it can and does drop. Reconnect rather than let it
        # crash the whole voice session; the same app_graph/thread_id are
        # reused, so conversation state (and the customer's demo login)
        # survive a reconnect untouched.
        while True:
            try:
                async with DeepgramTranscriber(on_speech_started=on_speech_started) as transcriber:
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(pump_mic(transcriber))
                        tg.create_task(conversation_loop(transcriber, tts))
            except* Exception as eg:
                for exc in eg.exceptions:
                    print(f"[info] Reconnecting STT session ({exc})...")
                drain(audio_in_queue)
                drain(audio_out_queue)
                leftover.clear()
                speaking.clear()
                barge_in.clear()
                await asyncio.sleep(0.2)


def main():
    settings.validate()
    settings.validate_voice()
    init_db()

    customer_id = choose_customer()

    print("Voice session started (Deepgram + ElevenLabs). Start talking any time.")
    print("Press Ctrl+C to exit.")
    try:
        asyncio.run(run_session(customer_id))
    except KeyboardInterrupt:
        print("\nVoice session ended.")


if __name__ == "__main__":
    main()
