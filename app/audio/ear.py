import io
import queue
import numpy as np
import sounddevice as sd
from scipy.io import wavfile
from faster_whisper import WhisperModel
import webrtcvad

class AcousticEar:
    """
    Robust Automated Speech Capture for Coding.
    Uses dynamic energy thresholds and generous silence padding to prevent cut-offs.
    """
    def __init__(self, model_size: str = "base"):
        print("[Ear] Loading Faster-Whisper Model...")
        self.stt_model = WhisperModel(model_size, device="cpu", compute_type="int8")
        print("[Ear] Whisper Model Loaded Successfully on CPU.")
        self.sample_rate = 16000
        # Configuration tuning for programming pauses
        self.vad = webrtcvad.Vad(3)
        self.silence_limit = 1.8  # Allowed pause duration in seconds before processing
        self.threshold = 500      # Audio amplitude threshold for speech detection

    def listen(self, mouth_instance=None) -> str:
        """Continuously monitors audio and captures a complete block of speech."""
        print("\n[Ear] Listening... (Go ahead, speak at your own pace)")
        
        audio_buffer = []
        speech_started = False
        chunks_of_silence = 0
        
        # WebRTC VAD requires 10, 20, or 30ms frames.
        # 16000Hz * 0.03 seconds = 480 samples per frame
        frame_duration_ms = 30
        frame_size = int(self.sample_rate * (frame_duration_ms / 1000.0)) 
        
        max_silence_frames = int((self.silence_limit * 1000) / frame_duration_ms)
        # Synchronous audio capture stream
        with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='int16', blocksize=1024) as stream:
            while True:
                chunk, _ = stream.read(frame_size)
                # Convert numpy array to raw bytes for VAD
                raw_bytes = chunk.tobytes()
                is_speech = self.vad.is_speech(raw_bytes, self.sample_rate)

                if speech_started:
                    audio_buffer.append(chunk)
                    if not is_speech:
                        silence_frames += 1
                        if silence_frames > max_silence_frames:
                            print("[Ear] Stop condition met. Transcribing...")
                            break
                    else:
                        silence_frames = 0 
                else:
                    if is_speech:
                        print("[Ear] Voice detected, capturing recording...")
                        speech_started = True
                        audio_buffer.append(chunk)
                        
                        # --- BARGE-IN LOGIC ---
                        # If the AI is currently playing audio, stop it immediately!
                        if mouth_instance and mouth_instance.is_playing:
                            print("[Ear] Barge-in detected! Cutting off AI...")
                            mouth_instance.interrupt()

        if not audio_buffer:
            return ""
        print("[Ear] Saved debug_listening_test.wav to your folder. Listen to it!")
        # 1. First, create the audio_data variable
        try:
            audio_data = np.concatenate(audio_buffer, axis=0)
            
            # 2. NOW we can save it to the hard drive for debugging!
            wavfile.write("debug_listening_test.wav", self.sample_rate, audio_data)
            print("[Ear] Saved debug_listening_test.wav to your folder. Listen to it!")

            # 3. Continue with the normal transcription...
            wav_io = io.BytesIO()
            wavfile.write(wav_io, self.sample_rate, audio_data)
            wav_io.seek(0)

            segments, _ = self.stt_model.transcribe(
                wav_io,
                beam_size=1,
                language="en",
                condition_on_previous_text=False
            )

            text = "".join([segment.text for segment in segments]).strip()
            print(f"[Ear] Heard: '{text}'")
            return text
            
        except Exception as e:
            print(f"[Ear Error] Transcription failure: {e}")
            return ""

    def close(self):
        pass