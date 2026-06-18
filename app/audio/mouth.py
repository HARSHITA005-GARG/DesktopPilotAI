import asyncio
import os
import queue
import threading
import subprocess
import numpy as np
import requests
import sounddevice as sd
from pathlib import Path
import re

class SentenceBuffer:
    """
    Incrementally splits streamed text into sentences.
    Silently ignores code blocks and splits on natural pauses for instant TTS.
    """
    def __init__(self):
        self._buffer = ""
        self._in_code_block = False
        # Matches terminal punctuation AND natural conversational pauses
        self.split_pattern = re.compile(r'([.?!,;:—]+)\s*')

    def push(self, text: str) -> list[str]:
        sentences = []
        for character in text:
            self._buffer += character
            
            # Detect Markdown Code Blocks (```)
            if self._buffer.endswith("```"):
                self._in_code_block = not self._in_code_block
                self._buffer = "" # Clear the backticks
                continue
                
            if self._in_code_block:
                continue

            # Split on natural pauses and terminal punctuation
            if character in ".?!,;:—":
                # Only split if it's a meaningful chunk, not just a stray comma
                if len(self._buffer.strip()) > 2: 
                    clean_sentence = self._buffer.replace("*", "").replace("`", "").strip()
                    if clean_sentence:
                        sentences.append(clean_sentence)
                    self._buffer = ""
                
        return sentences

    def flush(self) -> str | None:
        if self._in_code_block:
            self._buffer = ""
            return None
            
        remainder = self._buffer.replace("*", "").replace("`", "").strip()
        self._buffer = ""
        return remainder or None
    

class AcousticMouth:
    """
    The TTS Vocalization Engine.
    Upgraded for ordered streaming synthesis, thread safety, and robust sentence chunking.
    """

    def __init__(self, model_filename: str = "en_US-lessac-medium.onnx"):
        print("[Mouth] Initializing Piper TTS Engine...")
        self._closed = False
        self.sample_rate = 22050
        self.tts_queue = queue.Queue()
        self.is_speaking = False
        self._stop_flag = False
        


        # Dynamically resolve the absolute path to the model
        current_dir = Path(__file__).parent
        self.model_path = str(current_dir / "models" / model_filename)
        # Safety Check: Warn if the model or its JSON config is missing
        if not os.path.exists(self.model_path):
            print(f"[CRITICAL] Piper model NOT FOUND at: {self.model_path}")
        if not os.path.exists(f"{self.model_path}.json"):
            print(f"[CRITICAL] Piper JSON config NOT FOUND at: {self.model_path}.json")
        # Two queues: One for text waiting to be synthesized, one for audio waiting to be played
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        self.interrupt_event = threading.Event()

        self.is_playing = False

        # Start the ordered background workers
        self.synthesis_thread = threading.Thread(target=self._synthesis_worker, daemon=True)
        self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)

        self.synthesis_thread.start()
        self.playback_thread.start()

    def _synthesis_worker(self) -> None:
        """Continuously pulls text chunks in exact order and synthesizes them."""
        while True:
            text = self.text_queue.get()
            if text is None:
                self.text_queue.task_done()
                break

            if self.interrupt_event.is_set():
                self.text_queue.task_done()
                continue

            self._synthesize_and_queue_audio(text)
            self.text_queue.task_done()

    def _playback_worker(self) -> None:
        """Run the async chunk playback loop in a background thread."""
        asyncio.run(self._playback_loop())

    async def audio_chunk_stream(self):
        """Yield queued audio chunks asynchronously without blocking the agent loop."""
        while not self._closed:
            try:
                audio_data = self.audio_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue

            if audio_data is None:
                self.audio_queue.task_done()
                break

            self.audio_queue.task_done()
            yield audio_data

    async def _playback_loop(self) -> None:
        """Consume audio chunks in an async loop and play them one by one."""
        async for audio_data in self.audio_chunk_stream():
            if self.interrupt_event.is_set():
                continue

            self.is_playing = True
            try:
                sd.play(audio_data, samplerate=self.sample_rate)
                sd.wait()
            except Exception as e:
                print(f"[Mouth Error] Playback failed: {e}")
            finally:
                self.is_playing = False

    def _synthesize_and_queue_audio(self, text: str) -> None:
        """Executes the Piper binary and queues the audio. (Called only by the synthesis worker)"""
        if not text.strip():
            return
        try:
            if not os.path.exists(self.model_path):
                print(f"[Mouth Error] Cannot run Piper. File missing: {self.model_path}")
                return
            process = subprocess.Popen(
                ["piper", "-m", self.model_path, "--output_raw"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            raw_audio, stderr_data = process.communicate(input=text.encode('utf-8'))

            if not raw_audio:
                error_msg = stderr_data.decode('utf-8').strip()
                # If error_msg is empty, Piper crashed before it could write an error
                if not error_msg:
                    error_msg = "Silent crash. Verify Piper is installed correctly and your .onnx model is valid."
                print(f"[Mouth Error] Piper CLI failed. Details: {error_msg}")
                return
            
            audio_array = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
            audio_array = audio_array.reshape(-1, 1)
            stereo_array = np.concatenate((audio_array, audio_array), axis=1)
            
            self.audio_queue.put(stereo_array)
            
        except FileNotFoundError:
            print("[Mouth Error] 'piper' executable not found. Ensure piper-tts is installed.")
        except Exception as e:
            print(f"[Mouth Error] Synthesis failed: {e}")

    def queue_text(self, text: str) -> None:
        """Queue one spoken text segment for ordered background synthesis."""
        if text.strip():
            self.text_queue.put(text.strip())

    def interrupt(self) -> None:
        """Flush pending speech and cancel the current playback loop."""
        print("[Mouth] Interrupted! Stopping audio...")
        self.interrupt_event.set()
        self._flush_queues()
        sd.stop()
        self.interrupt_event.clear()

    def _flush_queues(self) -> None:
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
                self.text_queue.task_done()
            except queue.Empty:
                break
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except queue.Empty:
                break

    def speak_stream(self, llm_token_generator) -> str:
        """Queue complete sentences from an iterable of streamed text fragments."""
        sentence_buffer = SentenceBuffer()
        full_response = ""

        for token in llm_token_generator:
            full_response += token
            for sentence in sentence_buffer.push(token):
                self.queue_text(sentence)

        remainder = sentence_buffer.flush()
        if remainder:
            self.queue_text(remainder)

        return full_response

    def wait_until_done(self) -> None:
        """Blocks execution until both the text and audio queues are completely empty."""
        self.text_queue.join()
        self.audio_queue.join()

    async def async_wait_until_done(self) -> None:
        """Non-blocking wait path for the async agent loop."""
        await asyncio.to_thread(self.wait_until_done)

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        sd.stop()
        self.text_queue.put(None)
        self.audio_queue.put(None)
        self.synthesis_thread.join()
        self.playback_thread.join()
