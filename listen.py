"""Otto's ears: waits for you to talk, records until you stop, and turns it into text.

- webrtcvad + a loudness check decide what is real speech (so silence and room noise are ignored)
- Groq Whisper large-v3 turns the recording into text
"""
import os, io, time, queue, collections
import numpy as np
import sounddevice as sd
import soundfile as sf
import webrtcvad
import arabic_reshaper
from bidi.algorithm import get_display
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SILENCE_END = 0.7               # stop recording after 0.7 s of silence
MAX_SECONDS = 15                # longest question
MIN_LEVEL = 300                 # replaced by calibrate()
FAKE = {"شكرا", "موسيقى", "شكرا لكم", "شكرا للمشاهدة", "اشتركوا في القناة"}   # Whisper's "silence" words


def _pick_device():
    v = os.getenv("INPUT_DEVICE", "").strip()
    if v:
        return int(v)
    try:
        return sd.query_devices(kind="input")["index"]       # Windows default microphone
    except Exception:
        return sd.default.device[0]


def _pick_rate(dev):
    """webrtcvad only accepts 8/16/32/48 kHz, so use the mic's own rate if possible, otherwise one of those."""
    native = int(sd.query_devices(dev)["default_samplerate"])
    for r in [native, 48000, 16000, 32000]:
        if r in (8000, 16000, 32000, 48000):
            try:
                sd.check_input_settings(device=dev, samplerate=r, channels=1, dtype="int16")
                return r
            except Exception:
                pass
    raise SystemExit(f"Mic {dev} can't record at 16/32/48 kHz - pick another one with: python tools\\find_mic.py")


DEVICE = _pick_device()
RATE = _pick_rate(DEVICE)
FRAME = int(RATE * 0.03)        # 30 ms pieces


def show(text):
    """Makes Arabic display the right way round in the Windows terminal (display only)."""
    return get_display(arabic_reshaper.reshape(text))


def level_of(data):
    return float(np.sqrt(np.mean(np.frombuffer(data, dtype=np.int16).astype(np.float32) ** 2)))


def calibrate(seconds=1.0):
    """Measures the room's background noise so only real speech counts."""
    global MIN_LEVEL
    audio = sd.rec(int(seconds * RATE), samplerate=RATE, channels=1, dtype="int16", device=DEVICE)
    sd.wait()
    noise = level_of(audio.tobytes())
    MIN_LEVEL = max(noise * 3, 300)
    return noise


def record_utterance(max_wait=10):
    """Waits for you to talk, records until you stop. Returns raw audio, or None if nobody spoke."""
    vad = webrtcvad.Vad(3)                       # 0 = relaxed ... 3 = strict
    q = queue.Queue()
    before = collections.deque(maxlen=10)        # keeps 0.3 s before you start
    voiced, started, speech_run, silent = [], False, 0, 0
    t0 = time.time()

    def callback(indata, frames, t, status):
        q.put(bytes(indata))

    with sd.RawInputStream(samplerate=RATE, blocksize=FRAME, device=DEVICE,
                           channels=1, dtype="int16", callback=callback):
        while True:
            data = q.get()
            if len(data) != FRAME * 2:
                continue
            speech = level_of(data) > MIN_LEVEL and vad.is_speech(data, RATE)
            if not started:
                before.append(data)
                speech_run = speech_run + 1 if speech else 0
                if speech_run >= 3:              # ~0.1 s of real speech -> start
                    started, voiced = True, list(before)
                elif time.time() - t0 > max_wait:
                    return None
            else:
                voiced.append(data)
                silent = 0 if speech else silent + 1
                if silent * 0.03 >= SILENCE_END or len(voiced) * 0.03 >= MAX_SECONDS:
                    break
    return b"".join(voiced)


def transcribe(pcm, language="ar"):
    buf = io.BytesIO()
    sf.write(buf, np.frombuffer(pcm, dtype=np.int16), RATE, format="WAV", subtype="PCM_16")
    r = client.audio.transcriptions.create(
        file=("speech.wav", buf.getvalue()), model="whisper-large-v3",
        language=language, temperature=0)
    text = r.text.strip()
    if text.strip(" .،!؟?") in FAKE:
        print(f"   (ignored made-up text: {show(text)})")
        return ""
    return text


if __name__ == "__main__":
    # Quick test: press Enter, talk, see what Otto heard.
    print(f"Mic: [{DEVICE}] {sd.query_devices(DEVICE)['name']} @ {RATE} Hz")
    print("Measuring room noise - stay quiet for 1 second...")
    noise = calibrate()
    print(f"   room noise {noise:.0f} -> speech must be louder than {MIN_LEVEL:.0f}")
    while True:
        input("\nPress Enter and talk (Ctrl+C to quit)... ")
        print("Listening...")
        pcm = record_utterance()
        if pcm is None:
            print("   (nobody spoke)")
            continue
        t0 = time.time()
        text = transcribe(pcm)
        print(f"   recorded {len(pcm) / 2 / RATE:.1f}s | understood in {time.time() - t0:.1f}s")
        print(f"   You: {show(text) if text else '(nothing)'}")
