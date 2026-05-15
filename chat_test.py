import chromadb
from sentence_transformers import SentenceTransformer
import torch

# --- 1. Load the same embedding model used for indexing ---
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Loading model on {device}...")
model = SentenceTransformer("google/embeddinggemma-300M").to(device)

# --- 2. Connect to your existing vector database ---
client = chromadb.PersistentClient(path="./my_vectordb")
collection = client.get_collection("my_chunks")

print("\n✅ RAG system ready! Type 'exit' to quit.\n")

while True:
    # Get user input
    question = input("\n🤔 Your question: ").strip()
    
    if question.lower() in ["exit", "quit"]:
        print("Goodbye!")
        break
    
    if not question:
        continue
    
    # 3. Find relevant chunks
    query_embedding = model.encode([question], convert_to_tensor=False).tolist()
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=3,
        include=["documents", "metadatas"]
    )
    
    # 4. Display results
    print("\n📚 Relevant info found:\n")
    
    for i, (doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0])):
        # Show the metadata type and content preview
        doc_type = meta.get('type', 'unknown')
        title = meta.get('title', 'No title')
        print(f"[{i+1}] {doc_type}: {title}")
        print(f"    {doc[:300]}...\n")
    
    # 5. Optional: Send to an LLM for generation
    # (We'll add the LLM part next)