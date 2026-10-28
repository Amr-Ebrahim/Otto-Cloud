"""Finds your best microphone.

Lists your mics, records the same sentence from the ones you choose, and shows what Whisper heard.
Put the number of the clearest one in .env as INPUT_DEVICE.

Run from the project folder:  python tools\\find_mic.py
"""
import os
import numpy as np
import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
SECONDS = 5

print("Your microphones:")
for n, d in enumerate(sd.query_devices()):
    api = sd.query_hostapis(d["hostapi"])["name"]
    if d["max_input_channels"] > 0 and api in ("MME", "Windows WASAPI"):
        print(f"   [{n}] {d['name']}  ({api}, {int(d['default_samplerate'])} Hz)")

choice = input("\nType the numbers to test, separated by spaces (e.g. 1 20 3): ")
results = []
for dev in [int(x) for x in choice.split()]:
    try:
        info = sd.query_devices(dev)
        rate = int(info["default_samplerate"])
        input(f"\n[{dev}] {info['name']}\nPress Enter, then say: إزيك يا أوتو، إيه الأخبار النهارده؟ ")
        print(f"Recording {SECONDS} seconds...")
        audio = sd.rec(int(SECONDS * rate), samplerate=rate, channels=1, dtype="float32", device=dev)
        sd.wait()
        audio = audio[:, 0]
        peak = float(np.abs(audio).max())
        if peak > 0:
            audio = audio / peak * 0.9
        name = f"mic_{dev}.wav"
        sf.write(name, audio, rate)
        with open(name, "rb") as f:
            r = client.audio.transcriptions.create(
                file=(name, f.read()), model="whisper-large-v3", language="ar", temperature=0)
        results.append(f"[{dev}] {info['name']} | peak {peak:.3f} | -> {r.text.strip()}")
        print("   done")
    except Exception as e:
        results.append(f"[{dev}] ERROR: {e}")
        print(f"   error: {e}")

with open("mic_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(results))
print("\nFinished. Open mic_results.txt, listen to the mic_*.wav files, and pick the clearest one.")
print("A peak near 0.000 means that mic heard nothing.")
