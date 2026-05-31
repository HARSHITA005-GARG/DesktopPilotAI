import os
import re
import queue
import threading
import subprocess
import numpy as np
import sounddevice as sd

class AcousticMouth:
    """
    The TTS Vocalization Engine.
    Chunks streaming text into sentences and plays them sequentially to overlap 
    generation latency with audio playback.
    """
    
    def __init__(self, model_path: str = "./audio/models/en_US-lessac-medium.onnx"):
        print("[Mouth] Initializing Piper TTS Engine via standalone binary...")
        self.model_path = model_path
        # The Lessac voice model generates audio at 22050 Hz
        self.sample_rate = 22050 
        
        self.audio_queue = queue.Queue()
        self.is_playing = False
        
        self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self.playback_thread.start()

    def _playback_worker(self) -> None:
        """Continuously checks the queue for generated audio and plays it."""
        while True:
            audio_data = self.audio_queue.get()
            
            if audio_data is None:
                break 
                
            self.is_playing = True
            try:
                sd.play(audio_data, samplerate=self.sample_rate)
                sd.wait() 
            except Exception as e:
                print(f"[Mouth Error] Playback failed: {e}")
            finally:
                self.is_playing = False
                self.audio_queue.task_done()

    def _synthesize_and_queue(self, text: str) -> None:
        """Passes text to the Piper executable and captures raw PCM audio into RAM."""
        if not text.strip():
            return
            
        print(f"[Mouth] Synthesizing: {text}")
        try:
            # Bypass the broken Python wrapper and call the CLI tool directly.
            # --output_raw tells Piper to skip WAV headers and stream pure audio data.
            process = subprocess.Popen(
                ["piper", "-m", self.model_path, "--output_raw"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Send the text and extract the raw audio bytes
            raw_audio, stderr_data = process.communicate(input=text.encode('utf-8'))
            
            if not raw_audio:
                error_msg = stderr_data.decode('utf-8').strip()
                print(f"[Mouth Error] Piper CLI dropped audio. Stderr: {error_msg}")
                return
                
            # Convert raw bytes to numpy array
            audio_array = np.frombuffer(raw_audio, dtype=np.int16)
            
            # Scale to Float32 
            audio_array = audio_array.astype(np.float32) / 32768.0
            
            # Reshape to Mono
            audio_array = audio_array.reshape(-1, 1)
            
            # Duplicate for Stereo Bluetooth Headphones
            stereo_array = np.concatenate((audio_array, audio_array), axis=1)
            
            duration = len(audio_array) / self.sample_rate
            print(f"[Mouth] Sending {duration:.2f} seconds of stereo audio...")
            
            self.audio_queue.put(stereo_array)
            
        except FileNotFoundError:
            print("[Mouth Error] 'piper' executable not found. Ensure piper-tts is installed via uv.")
        except Exception as e:
            print(f"[Mouth Error] Synthesis failed: {e}")

    def speak_stream(self, llm_token_generator) -> str:
        """Buffers LLM tokens into sentences, then triggers TTS."""
        text_buffer = ""
        full_response = ""
        sentence_end_pattern = re.compile(r'([.?!])\s')

        for token in llm_token_generator:
            text_buffer += token
            full_response += token
            
            match = sentence_end_pattern.search(text_buffer)
            if match:
                split_index = match.end()
                sentence = text_buffer[:split_index].strip()
                
                threading.Thread(target=self._synthesize_and_queue, args=(sentence,)).start()
                text_buffer = text_buffer[split_index:]

        if text_buffer.strip():
            self._synthesize_and_queue(text_buffer.strip())

        return full_response

    def wait_until_done(self) -> None:
        """Blocks execution until the audio queue is empty."""
        self.audio_queue.join()
        while self.is_playing:
            pass