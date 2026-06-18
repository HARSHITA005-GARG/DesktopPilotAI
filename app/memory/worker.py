import threading
import queue
from memory.hybrid_db import HybridMemory

class MemoryWorker:
    """
    A dedicated background thread for LLM memory consolidation.
    Prevents the Graph/Vector extraction process from blocking the real-time audio loop.
    """
    
    def __init__(self):
        # 1. Initialize the thread-safe queue
        self.memory_queue = queue.Queue()
        
        # 2. Initialize the Hybrid DB strictly within this worker
        self.db = HybridMemory()
        
        # 3. Spin up the background daemon thread
        # daemon=True ensures this thread dies automatically when you close the main app
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

    def _process_queue(self) -> None:
        print("[Memory Worker] Background thread active and waiting...")
        while True:
            try:
                memory_id, raw_text = self.memory_queue.get()
                if raw_text is None:
                    break
                
                # Extract and store in memory, but DO NOT write to disk yet
                self.db.save_memory(memory_id, raw_text, persist=False)
                self.memory_queue.task_done()
                
                # If the queue is empty, we are done processing the batch. Now write to disk.
                if self.memory_queue.empty():
                    print("[Memory Worker] Queue empty. Persisting Knowledge Graph to disk...")
                    self.db.persist_graph()
                
            except Exception as e:
                print(f"[Memory Worker Error] Failed to process memory: {e}")

    def add_to_queue(self, memory_id: str, raw_text: str) -> None:
        """
        The non-blocking method your LangGraph orchestrator will call.
        It instantly drops the data in the queue and returns.
        """
        self.memory_queue.put((memory_id, raw_text))

    def retrieve_context(self, query: str) -> str:
        """
        Exposes the fast semantic/graph retrieval method for the main thread to use.
        """
        return self.db.retrieve_hybrid_context(query)