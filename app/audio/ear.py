import numpy as np
import pyaudiowpatch as pyaudio
import torch
from faster_whisper import WhisperModel
# import webrtc_audio_processing as webrtc # Conceptual wrapper for WebRTC AEC

class AcousticEar:
    """
    The acoustic processing pipeline. 
    Captures mic input, cancels speaker echo via WASAPI loopback, detects voice activity, and transcribes.
    """
    
    def __init__(self, silence_threshold_ms: int = 500):
        self.chunk_size = 512
        self.sample_rate = 16000
        self.silence_threshold_frames = int((self.sample_rate / self.chunk_size) * (silence_threshold_ms / 1000.0))
        
        print("[Ear] Loading Faster-Whisper (INT8, CPU)...")
        # base.en is extremely fast and fits easily in system RAM
        self.stt_model = WhisperModel("base.en", device="cpu", compute_type="int8")
        
        print("[Ear] Loading Silero VAD...")
        # Silero VAD is lightweight and highly accurate for speech detection
        self.vad_model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad')
        self.get_speech_timestamps = utils[0]
        
        # # Initialize WebRTC AEC (Assuming a standard wrapper interface)
        # self.aec = webrtc.AudioProcessingModule(aec=True)
        # self.aec.set_stream_format(self.sample_rate, 1) # 16kHz Mono

        # Initialize PyAudio for Windows WASAPI
        self.p = pyaudio.PyAudio()

    def _get_wasapi_loopback_device(self) -> dict:
        """Finds the default Windows speaker output for loopback capture."""
        try:
            default_speakers = self.p.get_default_output_device_info()
            for i in range(self.p.get_device_count()):
                dev = self.p.get_device_info_by_index(i)
                if dev["isLoopbackDevice"] and dev["name"] == default_speakers["name"]:
                    return dev
        except Exception as e:
            print(f"[Ear Error] Could not find WASAPI loopback: {e}")
        return None

    def listen_and_transcribe(self) -> str:
        """
        A blocking loop that waits for the user to speak, captures the audio, 
        detects when they stop, and returns the transcribed text.
        """
        loopback_device = self._get_wasapi_loopback_device()
        default_mic = self.p.get_default_input_device_info()
        
        # Open streams
        mic_stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.sample_rate, 
                                 input=True, frames_per_buffer=self.chunk_size, 
                                 input_device_index=default_mic["index"])
                                 
        speaker_stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.sample_rate, 
                                     input=True, frames_per_buffer=self.chunk_size, 
                                     input_device_index=loopback_device["index"]) if loopback_device else None

        print("\n[Ear] Listening...")
        
        audio_buffer = []
        silence_counter = 0
        is_speaking = False

        while True:
            # 1. Read raw audio from microphone and speakers
            raw_mic_data = mic_stream.read(self.chunk_size, exception_on_overflow=False)
            mic_array = np.frombuffer(raw_mic_data, dtype=np.int16)
            
            clean_audio = mic_array
            
            # 2. WebRTC AEC: Subtract the speaker audio from the mic audio
            if speaker_stream:
                raw_speaker_data = speaker_stream.read(self.chunk_size, exception_on_overflow=False)
                # speaker_array = np.frombuffer(raw_speaker_data, dtype=np.int16)
                # clean_audio = self.aec.process_stream(mic_array, speaker_array)
                clean_audio = mic_array
            # 3. Convert to Float32 tensor for Silero VAD
            tensor_audio = torch.from_numpy(clean_audio.astype(np.float32) / 32768.0)
            
            # 4. Voice Activity Detection
            confidence = self.vad_model(tensor_audio, self.sample_rate).item()
            
            if confidence > 0.5:
                is_speaking = True
                silence_counter = 0
                audio_buffer.append(clean_audio)
            elif is_speaking:
                silence_counter += 1
                audio_buffer.append(clean_audio)
                
                # If silence exceeds the threshold (e.g., 500ms), stop capturing
                if silence_counter > self.silence_threshold_frames:
                    break

        # Cleanup streams
        mic_stream.stop_stream()
        mic_stream.close()
        if speaker_stream:
            speaker_stream.stop_stream()
            speaker_stream.close()

        # 5. Transcription Pipeline
        if len(audio_buffer) == 0:
            return ""
            
        print("[Ear] Transcribing...")
        # Concatenate chunks into a single audio array
        final_audio = np.concatenate(audio_buffer).astype(np.float32) / 32768.0
        
        # Faster-Whisper requires the audio to be in a specific format
        segments, _ = self.stt_model.transcribe(final_audio, beam_size=5, language="en")
        
        transcription = "".join([segment.text for segment in segments]).strip()
        print(f"[Ear] Heard: '{transcription}'")
        
        return transcription