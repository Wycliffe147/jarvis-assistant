import wave
import numpy as np
import sounddevice as sd
import time
import re
from jarvis.config import SAMPLE_RATE, SILENCE_THRESHOLD, AUDIO_FILE, SILENCE_TIMEOUT, CHUNK_DURATION, PRE_SPEECH_LIMIT, MAX_DURATION, CHUNK_SIZE, COLOR_GRAY, COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_BLUE, COLOR_RESET
from jarvis.ai import transcribe_audio
from jarvis import state

def save_wav(filepath: str, audio: np.ndarray, sample_rate: int = SAMPLE_RATE):
    pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(filepath, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())

def listen_for_wake_word(wake_word: str = "jarvis") -> str | None:
    if state.is_speaking:
        return None

    LISTEN_SECONDS = 2.0
    num_frames = int(SAMPLE_RATE * LISTEN_SECONDS)
    try:
        audio = sd.rec(num_frames, samplerate=SAMPLE_RATE, channels=1, dtype='float32')
        sd.wait()
        audio = audio[:, 0]

        energy = float(np.sqrt(np.mean(audio ** 2)))
        if energy < SILENCE_THRESHOLD:
            return None

        save_wav(AUDIO_FILE, audio)
        if state.is_speaking:
            return None
        text = transcribe_audio(AUDIO_FILE)
        if not text:
            return None

        wake_variants = [wake_word, "javis", "jevis", "jarvas", "jervais", "jervis", "davis"]
        text_lower = text.lower()
        matched_variant = next((v for v in wake_variants if v in text_lower), None)

        if matched_variant:
            print(f"{COLOR_GRAY}[Heard: {text}]{COLOR_RESET}", flush=True)
            command = re.sub(rf'(?i){matched_variant}[,\s]*', '', text).strip()
            return command
        else:
            return None

    except Exception as e:
        print(f"Wake word error: {e}")
    return None

def get_voice_input() -> str | None:
    if state.is_speaking:
        return None

    frames         = []
    speech_started = False
    silent_chunks  = 0
    total_chunks   = 0

    silence_limit     = int(SILENCE_TIMEOUT   / CHUNK_DURATION)
    pre_speech_chunks = int(PRE_SPEECH_LIMIT   / CHUNK_DURATION)
    max_chunks        = int(MAX_DURATION       / CHUNK_DURATION)

    print(f"{COLOR_GRAY}[Listening... speak when ready]{COLOR_RESET}")
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=CHUNK_SIZE) as stream:
            while total_chunks < max_chunks:
                # Check lock inside loop for safety
                if state.is_speaking:
                    return None

                chunk, _ = stream.read(CHUNK_SIZE)
                chunk = chunk[:, 0]
                frames.append(chunk.copy())
                total_chunks += 1

                energy = float(np.sqrt(np.mean(chunk ** 2)))

                if energy > SILENCE_THRESHOLD:
                    if not speech_started:
                        speech_started = True
                        print(f"{COLOR_GREEN}\u25cf Recording{COLOR_RESET}", end="\r")
                    silent_chunks = 0
                else:
                    if speech_started:
                        silent_chunks += 1
                        dots = "." * min(silent_chunks, int(silence_limit))
                        print(f"{COLOR_YELLOW}\u2026 {dots}{COLOR_RESET}        ", end="\r")
                        if silent_chunks >= silence_limit:
                            break
                    else:
                        if total_chunks >= pre_speech_chunks:
                            print(f"{COLOR_RED}No speech detected.{COLOR_RESET}")
                            return None

        if not speech_started:
            print(f"{COLOR_RED}No speech detected.{COLOR_RESET}")
            return None

        sd.stop()
        time.sleep(0.3)

        print(f"{COLOR_GRAY}[Transcribing...]      {COLOR_RESET}")
        audio = np.concatenate(frames)
        save_wav(AUDIO_FILE, audio)
        if state.is_speaking:
            return None
        text = transcribe_audio(AUDIO_FILE)

        # Filter out low-signal/noise transcriptions (e.g., ".", "...", or just whitespace)
        if text:
            clean_text = text.strip().replace(".", "").strip()
            if not clean_text:
                print(f"{COLOR_GRAY}[Ignoring low-signal input: \"{text}\"]{COLOR_RESET}")
                return None

        if text:
            print(f"{COLOR_BLUE}You (Voice):{COLOR_RESET} {text}")
            return text
        else:
            print("Could not transcribe audio.")
            return None
    except Exception as e:
        print(f"\nVoice Error: {e}")
        return None
