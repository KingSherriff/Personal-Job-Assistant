import time
import torch
import ollama
import chromadb
from sentence_transformers import SentenceTransformer

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

HALLUCINATION_SIGNALS = [
    "as an ai", "i don't have personal", "i cannot", "i'm not able to",
    "as a language model", "developed by", "my training", "i don't possess",
    "i am an ai", "i was created by", "i don't have access",
]

FALLBACK = (
    "I don't have enough detail in Sherriff's portfolio to answer that confidently. "
    "Feel free to reach out at Sherriff.kadiri@outlook.com or visit "
    "https://github.com/KingSherriff."
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

def retrieve_context(query_embedding: list, n_fetch=7, n_keep=3) -> str:
    results = collection.query(query_embeddings=query_embedding, n_results=n_fetch)
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    seen_types = {}
    deduped = []
    for doc, meta in zip(docs, metas):
        chunk_type = meta.get("type", "unknown")
        if chunk_type not in seen_types:
            seen_types[chunk_type] = True
            deduped.append(doc)
        if len(deduped) == n_keep:
            break
    return "\n\n---\n\n".join(deduped)

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
    print(f"[Ollama stats] total={result['total_duration']/1e9:.1f}s, "
          f"prompt_eval={result['prompt_eval_duration']/1e9:.2f}s, "
          f"eval={result['eval_duration']/1e9:.2f}s, "
          f"tokens={result['eval_count']}")
    return result["message"]["content"].strip()

# ---------- Realistic Recruiter Questions ----------
questions = [
    "why should I hire him?",
    "What is Sherriff's current availability and what types of roles is he open to?",
    "Can you give me a quick summary of his strongest technical skills?",
    "What has he actually built—walk me through a couple of his key projects.",
    "What cloud and DevOps experience does he have? I want to know which platforms and CI/CD tools he’s used in practice.",
    "I see a short stint at Cashco Financial. Why did that end, and did he still get anything out of it?",
    "What makes him different from other DevOps or AI candidates I might be talking to?",
]

print("Running automatic question set ...\n")
for q in questions:
    print(f"\n> {q}")
    t0 = time.time()
    normalized = normalize_query(q)
    q_emb = embedder.encode([normalized], convert_to_tensor=False).tolist()
    t1 = time.time()

    context = retrieve_context(q_emb)
    t2 = time.time()

    user_message = f"""Question: {q}

Context from Sherriff's portfolio:
---
{context}
---

Answer the question using only the context above."""

    answer = ask_llm(SYSTEM_PROMPT, user_message)
    t3 = time.time()

    if is_hallucinating(answer):
        answer = FALLBACK

    print(f"Assistant: {answer}")
    print(f"[Timings] Embed: {t1-t0:.2f}s | Retrieve: {t2-t1:.3f}s | LLM: {t3-t2:.2f}s")

print("\nAll questions answered.")