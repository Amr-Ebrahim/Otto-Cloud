"""Otto's wake word: listens offline for "Hey Otto".

Two-stage check, because the wake-word model's scores vary a lot from one "Hey Otto" to the next:
  1. openWakeWord scores every 80 ms of sound (runs on your laptop, free).
  2. Score >= SURE  -> wake straight away.
     Score >= THRESHOLD ("maybe") -> send the last 2 s to Whisper and wake only if it heard the name.
"""
import os, re, time, queue, collections
import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly
from dotenv import load_dotenv
from openwakeword.model import Model
from listen import DEVICE, RATE, transcribe

load_dotenv()
THRESHOLD = float(os.getenv("WAKE_THRESHOLD", "0.04"))   # "maybe" -> double-check with Whisper
SURE = 0.25                                               # this high -> wake straight away
STEP = RATE * 80 // 1000                                  # 80 ms of audio
# "hey" + a word starting with o/u (Hey Otto / O2 / old / Udo), or the name itself
NAME = re.compile(r"hey[ou]|hio|ott?o|outo|auto|oto|udo|uto|odo|وتو|وطو|ودو")

model = Model(wakeword_models=["models/hey_otto.onnx"], inference_framework="onnx")


def is_otto(text):
    letters = re.sub(r"[^a-z0-9؀-ۿ]", "", text.lower())   # "Hey, O2." -> "heyo2"
    return bool(NAME.search(letters))


def wait_for_wake():
    """Listens until it hears 'Hey Otto'. Returns the score."""
    q = queue.Queue()
    recent = collections.deque(maxlen=25)                 # the last 2 s of sound

    def callback(indata, frames, t, status):
        q.put(indata[:, 0].copy())

    model.reset()
    ignore_until = 0.0
    with sd.InputStream(samplerate=RATE, blocksize=STEP, device=DEVICE,
                        channels=1, dtype="int16", callback=callback):
        while True:
            x = q.get()
            recent.append(x)
            x16 = np.clip(resample_poly(x.astype(np.float32), 16000, RATE), -32768, 32767).astype(np.int16)
            score = max(model.predict(x16).values())
            if score < THRESHOLD or time.time() < ignore_until:
                continue
            if score >= SURE:
                return score
            text = transcribe(np.concatenate(recent).tobytes(), language="en")   # double-check in English
            if is_otto(text):
                return score
            print(f"   (not 'Hey Otto': {text or '...'} | score {score:.2f})")
            model.reset()
            ignore_until = time.time() + 1.5
            while not q.empty():                          # skip sound that piled up while checking
                q.get()
