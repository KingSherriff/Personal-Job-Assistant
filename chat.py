# import os
import torch
import ollama
import chromadb
# from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# load_dotenv()
# HF_TOKEN = os.getenv("HF_TOKEN")
device = "cuda" if torch.cuda.is_available() else "cpu"
embedder = SentenceTransformer("all-mpnet-base-v2").to(device)

client = chromadb.PersistentClient(path="./my_vectordb")
collection = client.get_collection("my_chunks")
SYSTEM_PROMPT = (
    "You are Sherriff Kadiri's portfolio assistant. "
    "Use ONLY the context below to answer. "
    "If the answer isn't in the context, say exactly: "
    "'I don't have that detail — contact Sherriff.kadiri@outlook.com or visit https://github.com/KingSherriff.' "
    "Keep responses under 4 sentences. Never mention you are an AI."
)

def normalize_query(raw: str) -> str:
    lower = raw.lower().strip()
    replacements = {
        "does he":      "does Sherriff Kadiri",
        "is he":        "is Sherriff Kadiri",
        "has he":       "has Sherriff Kadiri",
        "can he":       "can Sherriff Kadiri",
        "did he":       "did Sherriff Kadiri",
        "his ":         "Sherriff Kadiri's ",
        "he ":          "Sherriff Kadiri ",
        "how many years": "how many years of experience does Sherriff Kadiri have",
    }
    for k, v in replacements.items():
        lower = lower.replace(k, v)
    return lower

def retrieve_context(query_embedding: list, n_fetch: int = 5, n_keep: int = 3) -> str:
    results = collection.query(query_embeddings=query_embedding, n_results=n_fetch)
    docs      = results["documents"][0]
    metas     = results["metadatas"][0]
    # distances = results["distances"][0]

    seen_types: dict = {}
    deduped: list[str] = []

    for doc, meta in zip(docs, metas):
        chunk_type = meta.get("type", "unknown")
        if chunk_type not in seen_types:
            seen_types[chunk_type] = True
            deduped.append(doc)
        if len(deduped) == n_keep:
            break

    return "\n\n---\n\n".join(deduped)

HALLUCINATION_SIGNALS = [
    "as an ai",
    "i don't have personal",
    "i cannot",
    "i'm not able to",
    "as a language model",
    "developed by",
    "my training",
    "i don't possess",
    "i am an ai",
    "i was created by",
    "i don't have access",
]

FALLBACK = (
    "I don't have enough detail in Sherriff's portfolio to answer that confidently. "
    "Feel free to reach out at Sherriff.kadiri@outlook.com or visit "
    "https://github.com/KingSherriff."
)

def is_hallucinating(response: str) -> bool:
    lower = response.lower()
    return any(signal in lower for signal in HALLUCINATION_SIGNALS)


def ask_llm(system: str, user: str) -> str:
    result = ollama.chat(
        model="gemma2:2b",
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        options={"temperature": 0.3, "num_predict": 200, "num_ctx": 1024},
    )
    # Print Ollama's own breakdown
    print(f"[Ollama stats] total={result['total_duration']/1e9:.1f}s, "
          f"prompt_eval={result['prompt_eval_duration']/1e9:.2f}s, "
          f"eval={result['eval_duration']/1e9:.2f}s, "
          f"tokens={result['eval_count']}")
    return result["message"]["content"].strip()


print("RAG Chatbot ready")

while True:
    question = input("\n> ").strip()
    if not question or question.lower() in ["exit", "quit"]:
        break
    normalized = normalize_query(question)
    q_emb = embedder.encode([normalized], convert_to_tensor=False).tolist()
    context = retrieve_context(q_emb)
    user_message = f"""Question: {question}

Context from Sherriff's portfolio:
---
{context}
---

Answer the question using only the context above."""

    answer = ask_llm(SYSTEM_PROMPT, user_message)

    if is_hallucinating(answer):
        answer = FALLBACK

    print(f"\nAssistant: {answer}")