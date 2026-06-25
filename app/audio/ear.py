import io
import os
import webrtcvad
import numpy as np
import sounddevice as sd
from scipy.io import wavfile
from groq import Groq  # Uses your existing groq dependency
from faster_whisper import WhisperModel
class AcousticEar:
    """
    Ultra-efficient Speech Capture powered by Groq Cloud Whisper.
    Uses local WebRTC VAD for endpointing, and cloud hardware for flawless accuracy.
    """
    def __init__(self):
        print("[Ear] Connecting to Groq Audio Cloud...")
        # Initialize Groq client using your existing environment variable
        self.groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        print("[Ear] Groq Audio Pipeline Connected Successfully.")

        print("[Ear] Loading Local Fallback Model (CPU)...")
        self.local_stt = WhisperModel("base", device="cpu", compute_type="int8")
        print("[Ear] Local Fallback Model Loaded.")
        self.sample_rate = 16000
        self.vad = webrtcvad.Vad(3) # Aggressive filtering for background noise
        
        # 1.8 seconds allows you to pause and think without getting cut off
        self.silence_limit = 1.8  

    def listen(self, mouth_instance=None) -> str:
        print("\n[Ear] Listening... (Speak naturally, take your time)")
        
        audio_buffer = []
        speech_started = False
        silence_frames = 0
        
        # 30ms audio frame layout required by WebRTC VAD
        frame_duration_ms = 30
        frame_size = int(self.sample_rate * (frame_duration_ms / 1000.0)) 
        max_silence_frames = int((self.silence_limit * 1000) / frame_duration_ms)

        with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='int16', blocksize=frame_size) as stream:
            while True:
                chunk, _ = stream.read(frame_size)
                raw_bytes = chunk.tobytes()
                is_speech = self.vad.is_speech(raw_bytes, self.sample_rate)

                if speech_started:
                    audio_buffer.append(chunk)
                    if not is_speech:
                        silence_frames += 1
                        if silence_frames > max_silence_frames:
                            print("[Ear] Punctuation point met. Transcribing via Groq Cloud...")
                            break
                    else:
                        silence_frames = 0 
                else:
                    if is_speech:
                        print("[Ear] Voice detected, recording stream...")
                        speech_started = True
                        audio_buffer.append(chunk)
                        
                        # Barge-in: Cut off the AI instantly if it's currently speaking
                        if mouth_instance and mouth_instance.is_playing:
                            print("[Ear] User interruption detected! Halting AI speech...")
                            mouth_instance.interrupt()

        if not audio_buffer:
            return ""
        # Flatten audio buffer data into traditional wave architecture
        audio_data = np.concatenate(audio_buffer, axis=0)
        
        # Write audio purely to an in-memory byte buffer (No slow disk read/writes!)
        wav_io = io.BytesIO()
        wavfile.write(wav_io, self.sample_rate, audio_data)
        wav_io.name = "audio.wav" 
        wav_io.seek(0)
        try:
            # Fire the audio data off to Groq's massive Whisper Large cluster
            transcription = self.groq_client.audio.transcriptions.create(
                file=wav_io,
                model="whisper-large-v3",
                language="en",
                response_format="json",
                timeout=30
            )

            text = transcription.text.strip()
            print(f"[Ear] Heard Perfectly: '{text}'")
            return text
            
        except Exception as e:
            # 2. If no internet or API fails, drop to local hardware
            print(f"\n[Ear] Cloud unavailable. Rerouting to local hardware...")
            wav_io.seek(0) # Reset the byte buffer
            
            segments, _ = self.local_stt.transcribe(
                wav_io,
                beam_size=1,
                language="en",
                condition_on_previous_text=False
            )
            text = "".join([segment.text for segment in segments]).strip()
            print(f"[Ear] Heard (Local Fallback): '{text}'")
            return text

    def close(self):
        pass