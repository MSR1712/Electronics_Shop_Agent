"""
Browser voice bridge. Same design as interfaces/voice_app.py — Deepgram
(STT) + ElevenLabs (TTS) are I/O only, every finalized customer utterance
goes through handle_customer_message(text), and the same build_graph() the
rest of the app uses remains the sole decision-maker — just over a
WebSocket instead of local mic/speaker (sounddevice) streams. Reuses
interfaces/voice_engine.py's DeepgramTranscriber/ElevenLabsSpeaker and
fixed sample rates directly rather than redefining them.

Wire protocol on /ws/voice (unchanged from the Gemini Live version — the
browser side, web/src/hooks/useVoiceCall.ts, needed no changes for this
swap):
  browser -> server (binary):  raw PCM16 mono @ INPUT_SAMPLE_RATE  (16kHz)
  server -> browser (binary):  raw PCM16 mono @ OUTPUT_SAMPLE_RATE (24kHz)
  server -> browser (text, JSON):
    {"type": "interrupted"}                         - flush playback now (barge-in)
    {"type": "transcript", "role": "user"|"assistant", "text": "..."}
    {"type": "error", "message": "..."}

Identity: customer_id/conversation_id come from the same signed session
cookie the rest of api/ uses (api/session.py), NOT from anything the
browser sends — so a voice-placed order lands in the exact same
conversation/customer as the chat widget and manual checkout on the same
browser session.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, HumanMessage

from config import settings
from interfaces.text_utils import extract_text
from interfaces.voice_engine import DeepgramTranscriber, ElevenLabsSpeaker

from api.session import get_ws_session

router = APIRouter()


async def _send_json(websocket: WebSocket, payload: dict) -> None:
    try:
        await websocket.send_text(json.dumps(payload))
    except Exception:
        pass


@router.websocket("/ws/voice")
async def voice_bridge(websocket: WebSocket) -> None:
    # CORSMiddleware does not cover WebSocket upgrades, so the origin check
    # that keeps api/ scoped to the known frontend has to happen here too.
    if websocket.headers.get("origin") != settings.frontend_origin:
        await websocket.close(code=4403)
        return

    session_data = get_ws_session(websocket)
    if session_data is None:
        await websocket.close(code=4401)
        return

    try:
        settings.validate_voice()
    except EnvironmentError as e:
        await websocket.accept()
        await _send_json(websocket, {"type": "error", "message": str(e)})
        await websocket.close(code=1011)
        return

    await websocket.accept()

    graph = websocket.app.state.graph
    customer_id = session_data.customer_id
    conversation_id = session_data.conversation_id

    async def handle_customer_message(text: str) -> str:
        """Identical shape to interfaces/voice_app.py's, but reusing this
        browser session's existing conversation_id instead of minting a new
        one, so a voice order joins the same conversation as this session's
        chat/checkout activity rather than starting a disconnected thread."""
        config = {"configurable": {"thread_id": conversation_id}}
        graph_input = {
            "messages": [HumanMessage(content=text)],
            "customer_id": customer_id,
            "conversation_id": conversation_id,
        }
        try:
            result = await asyncio.to_thread(graph.invoke, graph_input, config=config)
        except Exception:
            return "Sorry, something went wrong on our end. Could you try again?"

        if "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            return payload.get("message", "You're being connected to a human agent.")

        last_ai = next((m for m in reversed(result["messages"]) if isinstance(m, AIMessage)), None)
        return extract_text(last_ai.content) if last_ai else "Sorry, I did not catch that."

    tts = ElevenLabsSpeaker()
    speaking = asyncio.Event()
    barge_in = asyncio.Event()

    async def on_speech_started() -> None:
        # Deepgram has no idea whether the assistant is currently talking -
        # only treat this as a barge-in when it is. Sent immediately (not
        # left for the TTS loop to notice on its next chunk) so the browser
        # flushes playback as soon as possible - see useVoiceCall.ts's
        # flushPlayback, triggered by this exact message.
        if speaking.is_set() and not barge_in.is_set():
            barge_in.set()
            await _send_json(websocket, {"type": "interrupted"})

    async def pump_browser_audio_in(transcriber: DeepgramTranscriber) -> None:
        """Browser mic audio (binary WS frames) -> Deepgram. Raises
        WebSocketDisconnect when the browser hangs up, which cancels the
        sibling task via the enclosing TaskGroup."""
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            data = message.get("bytes")
            if data:
                await transcriber.send_audio(data)

    async def speak(text: str) -> None:
        speaking.set()
        barge_in.clear()
        try:
            async for chunk in tts.synthesize(text):
                if barge_in.is_set():
                    break
                await websocket.send_bytes(chunk)
        except Exception:
            pass
        finally:
            speaking.clear()

    async def conversation_loop(transcriber: DeepgramTranscriber) -> None:
        """Deepgram's finalized utterances -> graph -> ElevenLabs ->
        browser. Mirrors voice_app.py's conversation_loop."""
        while True:
            text = await transcriber.next_utterance()
            await _send_json(websocket, {"type": "transcript", "role": "user", "text": text})
            reply = await handle_customer_message(text)
            await _send_json(websocket, {"type": "transcript", "role": "assistant", "text": reply})
            await speak(reply)

    try:
        while True:
            # break/continue/return can't appear inside an except* block
            # (PEP 654), so the browser-hung-up case is signalled via this
            # flag and checked after the try/except* finishes instead.
            browser_disconnected = False
            try:
                async with DeepgramTranscriber(on_speech_started=on_speech_started) as transcriber:
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(pump_browser_audio_in(transcriber))
                        tg.create_task(conversation_loop(transcriber))
            except* WebSocketDisconnect:
                browser_disconnected = True
            except* Exception:
                await _send_json(websocket, {"type": "error", "message": "Reconnecting..."})

            if browser_disconnected:
                break
            speaking.clear()
            barge_in.clear()
            await asyncio.sleep(0.2)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
