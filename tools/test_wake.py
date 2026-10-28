"""Shows how strongly the wake-word model reacts to your "Hey Otto" (one line per second).

Use it to choose WAKE_THRESHOLD in .env: a bit below your weakest real "Hey Otto",
and well above what silence and normal talk give.

Run from the project folder:  python tools\\test_wake.py
"""
import sys, time, queue
from pathlib import Path
import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly
from openwakeword.model import Model

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from listen import DEVICE, RATE   # same mic as Otto

STEP = RATE * 80 // 1000
model = Model(wakeword_models=["models/hey_otto.onnx"], inference_framework="onnx")
q = queue.Queue()


def callback(indata, frames, t, status):
    q.put(indata[:, 0].copy())


log = open("wake_log.txt", "w", encoding="utf-8")
print("Stay quiet 5 s, then say 'Hey Otto' 5 times (3 s apart), then talk normally. Ctrl+C to stop.\n")
best, t_last, overall = 0.0, time.time(), 0.0
with sd.InputStream(samplerate=RATE, blocksize=STEP, device=DEVICE,
                    channels=1, dtype="int16", callback=callback):
    try:
        while True:
            x = q.get().astype(np.float32)
            x16 = np.clip(resample_poly(x, 16000, RATE), -32768, 32767).astype(np.int16)
            score = max(model.predict(x16).values())
            best, overall = max(best, score), max(overall, score)
            if time.time() - t_last >= 1.0:
                line = f"{best:.4f} " + "#" * int(best * 50)
                print(line)
                log.write(line + "\n"); log.flush()
                best, t_last = 0.0, time.time()
    except KeyboardInterrupt:
        pass
print(f"\nHighest score: {overall:.4f}")
log.write(f"Highest score: {overall:.4f}\n")
