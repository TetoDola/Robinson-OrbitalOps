import lameSource from "lamejs/lame.all.js?raw";

const SAMPLE_RATE = 22050;
const DURATION_SECONDS = 3.4;
const MP3_KBPS = 64;

interface LameRuntime {
  Mp3Encoder: new (channels: number, sampleRate: number, kbps: number) => {
    encodeBuffer(left: Int16Array, right?: Int16Array): Uint8Array;
    flush(): Uint8Array;
  };
}

interface FanAudioOptions {
  severity?: number;
}

let lameRuntime: LameRuntime | null = null;

function getLameRuntime(): LameRuntime {
  if (lameRuntime) {
    return lameRuntime;
  }
  // lamejs' CommonJS entrypoint leaks internal names under Vite. Its bundled
  // browser source is self-contained, so evaluate that once and keep the API.
  lameRuntime = new Function(`${lameSource}; return lamejs;`)() as LameRuntime;
  return lameRuntime;
}

function smoothstep(edge0: number, edge1: number, value: number): number {
  const t = Math.max(0, Math.min(1, (value - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

function chirp(t: number, start: number, duration: number): number {
  const local = t - start;
  if (local < 0 || local > duration) {
    return 0;
  }
  const p = local / duration;
  const envelope = Math.sin(Math.PI * p);
  const hz = 1180 + 460 * p;
  return Math.sin(2 * Math.PI * hz * local) * envelope;
}

function seededNoise(seed: number): () => number {
  let value = seed >>> 0;
  return () => {
    value = (1664525 * value + 1013904223) >>> 0;
    return value / 0xffffffff;
  };
}

function synthFanPcm({ severity = 1 }: FanAudioOptions = {}): Int16Array {
  const sampleCount = Math.floor(SAMPLE_RATE * DURATION_SECONDS);
  const pcm = new Int16Array(sampleCount);
  const noise = seededNoise(0x0f57c001);
  let rumble = 0;

  for (let i = 0; i < sampleCount; i += 1) {
    const t = i / SAMPLE_RATE;
    const spinUp = smoothstep(0, 0.42, t);
    const sustain = 1 - smoothstep(DURATION_SECONDS - 0.38, DURATION_SECONDS, t) * 0.18;
    const envelope = spinUp * sustain;
    const wobble = Math.sin(2 * Math.PI * 0.62 * t);
    const bladeHz = 94 + severity * 12 + wobble * 5;
    const blade = Math.sin(2 * Math.PI * bladeHz * t);
    const harmonic = Math.sin(2 * Math.PI * bladeHz * 2.02 * t + 0.4) * 0.52;
    const bearing = Math.sin(2 * Math.PI * (720 + severity * 160 + wobble * 18) * t) * 0.17;
    const hiss = (noise() * 2 - 1) * 0.1;
    rumble = rumble * 0.94 + (noise() * 2 - 1) * 0.06;

    const clackPhase = (t * (9.5 + severity * 2.8)) % 1;
    const clack = clackPhase > 0.975 ? (noise() * 2 - 1) * 0.18 : 0;
    const warningTone = chirp(t, 1.02, 0.16) * 0.18 + chirp(t, 2.34, 0.18) * 0.16;
    const sample =
      envelope *
      (blade * 0.32 + harmonic * 0.22 + rumble * 0.72 + bearing + hiss + clack + warningTone);

    pcm[i] = Math.max(-1, Math.min(1, sample)) * 32767;
  }

  return pcm;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

export function renderFanAudioMp3DataUrl(options?: FanAudioOptions): string {
  const { Mp3Encoder } = getLameRuntime();
  const encoder = new Mp3Encoder(1, SAMPLE_RATE, MP3_KBPS);
  const pcm = synthFanPcm(options);
  const chunks: Uint8Array[] = [];
  const blockSize = 1152;

  for (let i = 0; i < pcm.length; i += blockSize) {
    const encoded = encoder.encodeBuffer(pcm.subarray(i, i + blockSize));
    if (encoded.length > 0) {
      chunks.push(new Uint8Array(encoded));
    }
  }

  const flushed = encoder.flush();
  if (flushed.length > 0) {
    chunks.push(new Uint8Array(flushed));
  }

  const totalLength = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const mp3Bytes = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    mp3Bytes.set(chunk, offset);
    offset += chunk.length;
  }

  return `data:audio/mpeg;base64,${bytesToBase64(mp3Bytes)}`;
}

export const FAN_AUDIO_DURATION_SECONDS = DURATION_SECONDS;
