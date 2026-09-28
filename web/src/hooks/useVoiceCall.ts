"use client";

import { useCallback, useRef, useState } from "react";
import { WS_BASE } from "@/lib/api";

export type VoiceStatus = "idle" | "connecting" | "active" | "error";
export type VoiceTranscript = { role: "user" | "assistant"; text: string };

type Options = {
  onTranscript?: (t: VoiceTranscript) => void;
  onError?: (message: string) => void;
};

// Fixed by the Gemini Live API, mirroring interfaces/voice_app.py's
// INPUT_SAMPLE_RATE / OUTPUT_SAMPLE_RATE — not tunable knobs.
const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;

/**
 * Browser-side half of api/routers/voice.py's /ws/voice bridge: captures
 * mic audio via an AudioWorklet, streams it as raw PCM16 over a WebSocket,
 * and schedules PCM16 audio chunks received back for gapless playback.
 * Barge-in ("interrupted" message) flushes whatever's still queued/playing
 * immediately, same as voice_app.py's speaker_callback does locally.
 */
export function useVoiceCall({ onTranscript, onError }: Options) {
  const [status, setStatus] = useState<VoiceStatus>("idle");

  const wsRef = useRef<WebSocket | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const micContextRef = useRef<AudioContext | null>(null);
  const playContextRef = useRef<AudioContext | null>(null);
  const nextStartTimeRef = useRef(0);
  const activeSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());

  const stop = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;

    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;

    micContextRef.current?.close().catch(() => {});
    micContextRef.current = null;

    for (const src of activeSourcesRef.current) {
      try {
        src.stop();
      } catch {
        // already stopped/ended
      }
    }
    activeSourcesRef.current.clear();

    playContextRef.current?.close().catch(() => {});
    playContextRef.current = null;

    setStatus((s) => (s === "error" ? s : "idle"));
  }, []);

  const flushPlayback = useCallback(() => {
    for (const src of activeSourcesRef.current) {
      try {
        src.stop();
      } catch {
        // already stopped/ended
      }
    }
    activeSourcesRef.current.clear();
    if (playContextRef.current) nextStartTimeRef.current = playContextRef.current.currentTime;
  }, []);

  const playChunk = useCallback((bytes: ArrayBuffer) => {
    const ctx = playContextRef.current;
    if (!ctx) return;

    const int16 = new Int16Array(bytes);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      const v = int16[i];
      float32[i] = v < 0 ? v / 0x8000 : v / 0x7fff;
    }

    const buffer = ctx.createBuffer(1, float32.length, OUTPUT_SAMPLE_RATE);
    buffer.copyToChannel(float32, 0);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    // Schedule back-to-back rather than starting immediately, so chunks
    // that arrive faster than real-time still play out gaplessly.
    const startAt = Math.max(nextStartTimeRef.current, ctx.currentTime);
    source.start(startAt);
    nextStartTimeRef.current = startAt + buffer.duration;

    activeSourcesRef.current.add(source);
    source.onended = () => activeSourcesRef.current.delete(source);
  }, []);

  const start = useCallback(async () => {
    setStatus("connecting");
    try {
      const micStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      micStreamRef.current = micStream;

      const micContext = new AudioContext({ sampleRate: INPUT_SAMPLE_RATE });
      micContextRef.current = micContext;
      await micContext.audioWorklet.addModule("/audio/mic-processor.js");
      const micSource = micContext.createMediaStreamSource(micStream);
      const workletNode = new AudioWorkletNode(micContext, "mic-processor");
      micSource.connect(workletNode);

      const playContext = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE });
      playContextRef.current = playContext;
      nextStartTimeRef.current = playContext.currentTime;

      const ws = new WebSocket(`${WS_BASE}/ws/voice`);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("active");
        workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
          if (ws.readyState === WebSocket.OPEN) ws.send(event.data);
        };
      };

      ws.onmessage = (event: MessageEvent<string | ArrayBuffer>) => {
        if (typeof event.data === "string") {
          try {
            const msg = JSON.parse(event.data) as { type: string; role?: "user" | "assistant"; text?: string; message?: string };
            if (msg.type === "interrupted") flushPlayback();
            else if (msg.type === "transcript" && msg.role && msg.text) onTranscript?.({ role: msg.role, text: msg.text });
            else if (msg.type === "error" && msg.message) onError?.(msg.message);
          } catch {
            // ignore malformed control frame
          }
        } else {
          playChunk(event.data);
        }
      };

      ws.onerror = () => onError?.("Voice connection error.");
      ws.onclose = () => stop();
    } catch (err) {
      setStatus("error");
      onError?.(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone permission denied."
          : err instanceof Error
            ? err.message
            : "Could not start voice call."
      );
      stop();
    }
  }, [flushPlayback, playChunk, onTranscript, onError, stop]);

  return { status, start, stop };
}
