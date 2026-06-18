import os
import json
import networkx as nx
import chromadb
from sentence_transformers import SentenceTransformer
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

class HybridMemory:
    """
    An LLM-filtered Hybrid Graph/Vector Database.
    Extracts entities and relationships before saving to save space and improve recall.
    """
    
    def __init__(self, db_path: str = "./memory/data"):
        # 1. Vector Setup (ChromaDB)
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        os.makedirs(db_path, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=db_path)
        self.vector_collection = self.chroma_client.get_or_create_collection("hybrid_vectors")
        
        # 2. Graph Setup (NetworkX)
        self.graph_path = os.path.join(db_path, "knowledge_graph.graphml")
        if os.path.exists(self.graph_path):
            self.graph = nx.read_graphml(self.graph_path)
        else:
            self.graph = nx.DiGraph()

        # 3. LLM Setup for Consolidation
        # Point this to your local Ollama instance running the 8B model
        # 3. LLM Setup for Consolidation
        # Point this to your local Ollama instance running the 8B model
        self.llm = ChatOllama(model="llama3.2:3b", format="json", temperature=0)

    def _extract_knowledge_with_llm(self, text: str) -> dict:
        # ... prompt ...
        response = self.llm.invoke([HumanMessage(content=prompt)])
        
        # Strip markdown formatting
        raw_content = response.content.strip()
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:-3].strip()
        elif raw_content.startswith("```"):
            raw_content = raw_content[3:-3].strip()
            
        try:
            return json.loads(raw_content)
        except json.JSONDecodeError:
            print(f"[Memory Error] Failed to parse LLM JSON: {raw_content}")
            return {"facts": [], "relations": []}

    def save_memory(self, memory_id: str, raw_text: str, persist: bool = True) -> None:
        extracted_data = self._extract_knowledge_with_llm(raw_text)
        
        # 1. Save to Graph DB (Memory Only)
        for rel in extracted_data.get("relations", []):
            if rel.get("source") and rel.get("target") and rel.get("relationship"):
                self.graph.add_edge(rel["source"], rel["target"], label=rel["relationship"])
                
        # 2. Persist the graph only if requested
        if persist:
            self.persist_graph()
        
    def persist_graph(self) -> None:
        """Saves the NetworkX graph to the disk."""
        nx.write_graphml(self.graph, self.graph_path)

    def retrieve_hybrid_context(self, query: str) -> str:
        """
        Queries ChromaDB for semantic matches, then traverses the Graph to pull in related concepts.
        """
        if self.vector_collection.count() == 0:
            return ""

        # Step 1: Semantic Search
        query_embedding = self.embedding_model.encode(query).tolist()
        vector_results = self.vector_collection.query(
            query_embeddings=[query_embedding],
            n_results=2
        )
        
        documents = vector_results.get("documents", [[]])[0]
        if not documents:
            return ""

        context = "<hybrid_memory>\n"
        context += "Direct Facts:\n"
        for doc in documents:
            context += f"- {doc}\n"

        # Step 2: Graph Traversal (Find 1st degree connections)
        # We can extract entities from the query (or just use the graph if we know the nodes)
        # For simplicity, we dump a summary of relevant graph edges
        if self.graph.number_of_edges() > 0:
             context += "\nRelational Context:\n"
             # In a full implementation, you would match query keywords to graph nodes here.
             # This grabs a small sample of known relationships.
             for u, v, data in list(self.graph.edges(data=True))[:3]:
                 context += f"- {u} {data.get('label', 'is related to')} {v}\n"
                 
        context += "</hybrid_memory>"
        return context