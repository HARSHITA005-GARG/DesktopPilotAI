import numpy as np
import pyaudiowpatch as pyaudio
import torch
from faster_whisper import WhisperModel

class AcousticEar:
    """
    The acoustic processing pipeline. 
    Upgraded for better accent recognition and patient voice activity detection.
    """
    
    # 1. Increased silence threshold to 1200ms to prevent cutting you off mid-sentence
    def __init__(self, silence_threshold_ms: int = 1200):
        self.chunk_size = 512
        self.sample_rate = 16000
        self.silence_threshold_frames = int((self.sample_rate / self.chunk_size) * (silence_threshold_ms / 1000.0))
        
        print("[Ear] Loading Faster-Whisper 'small' model (INT8, CPU)...")
        # 2. Upgraded to 'small.en' for drastically better Indian English accent recognition
        self.stt_model = WhisperModel("small.en", device="cpu", compute_type="int8")
        
        print("[Ear] Loading Silero VAD...")
        self.vad_model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad')
        self.get_speech_timestamps = utils[0]
        
        self.p = pyaudio.PyAudio()

    def listen_and_transcribe(self) -> str:
        """
        Waits for the user to speak, patiently waits for them to stop, 
        and transcribes with high accuracy.
        """
        default_mic = self.p.get_default_input_device_info()
        
        mic_stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.sample_rate, 
                                 input=True, frames_per_buffer=self.chunk_size, 
                                 input_device_index=default_mic["index"])

        print("\n[Ear] Listening...")
        
        audio_buffer = []
        silence_counter = 0
        is_speaking = False

        while True:
            raw_mic_data = mic_stream.read(self.chunk_size, exception_on_overflow=False)
            mic_array = np.frombuffer(raw_mic_data, dtype=np.int16)
            
            # Convert to Float32 tensor for Silero VAD
            tensor_audio = torch.from_numpy(mic_array.astype(np.float32) / 32768.0)
            
            # Voice Activity Detection
            confidence = self.vad_model(tensor_audio, self.sample_rate).item()
            
            if confidence > 0.5:
                is_speaking = True
                silence_counter = 0  # Reset the silence counter every time you make a sound
                audio_buffer.append(mic_array)
            elif is_speaking:
                silence_counter += 1
                audio_buffer.append(mic_array)
                
                # If silence exceeds the new 1.2-second threshold, stop capturing
                if silence_counter > self.silence_threshold_frames:
                    break

        # Cleanup streams
        mic_stream.stop_stream()
        mic_stream.close()

        if len(audio_buffer) == 0:
            return ""
            
        print("[Ear] Transcribing...")
        final_audio = np.concatenate(audio_buffer).astype(np.float32) / 32768.0
        
        # 3. Added initial_prompt to give the model phonetic context
        segments, _ = self.stt_model.transcribe(
            final_audio, 
            beam_size=5, 
            language="en",
            initial_prompt="Hello! I am speaking conversational English. Can you help me with a coding task?"
        )
        
        transcription = "".join([segment.text for segment in segments]).strip()
        print(f"[Ear] Heard: '{transcription}'")
        
        return transcription