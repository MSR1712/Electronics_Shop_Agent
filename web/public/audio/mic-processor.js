// Runs on the browser's audio rendering thread (AudioWorkletGlobalScope).
// The AudioContext that owns this node must be created with
// `sampleRate: 16000` so `process()` already receives audio at the rate
// Gemini Live requires (see interfaces/voice_app.py's INPUT_SAMPLE_RATE) —
// no resampling math needed here, just Float32 -> PCM16 and chunking.
const CHUNK_SAMPLES = 1600; // 100ms @ 16kHz, matches voice_app.py's INPUT_BLOCK_SIZE

class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Int16Array(CHUNK_SAMPLES);
    this._offset = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      for (let i = 0; i < channel.length; i++) {
        const s = Math.max(-1, Math.min(1, channel[i]));
        this._buffer[this._offset++] = s < 0 ? s * 0x8000 : s * 0x7fff;
        if (this._offset === CHUNK_SAMPLES) {
          this.port.postMessage(this._buffer.buffer, [this._buffer.buffer]);
          this._buffer = new Int16Array(CHUNK_SAMPLES);
          this._offset = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("mic-processor", MicProcessor);
