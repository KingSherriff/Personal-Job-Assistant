import re
import time
import torch
import pickle
import ollama
import chromadb
from sentence_transformers import SentenceTransformer

device = "cuda" if torch.cuda.is_available() else "cpu"
embedder = SentenceTransformer("all-mpnet-base-v2").to(device)

client = chromadb.PersistentClient(path="./my_vectordb")
collection = client.get_collection("my_chunks")

all_data = collection.get(include=["documents", "metadatas"])
id_to_doc_meta = {all_data["ids"][i]: (all_data["documents"][i], all_data["metadatas"][i]) for i in range(len(all_data["ids"]))}
ordered_ids = list(id_to_doc_meta.keys())

with open('bm25_model.pkl', 'rb') as f:
    bm25 = pickle.load(f)

SYSTEM_PROMPT = (
    "You are Sherriff Kadiri's portfolio assistant. "
    "Answer using ONLY the information explicitly stated in the context below. "
    "If the context does not contain a direct or closely related answer, say exactly: "
    "'I don't have that detail - contact Sherriff.kadiri@outlook.com or visit https://github.com/KingSherriff.' "
    "Do not infer, generalise, or add any information not present in the context. "
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

def retrieve_context(query_bm25, query_embedding, n_fetch=10, n_keep=4) -> str:
    vector_relevance_importance_weight = 0.55
    rank_relevance_importance_weight = 0.4
    manual_rank_importance_weight = 1 - vector_relevance_importance_weight - rank_relevance_importance_weight


    results = collection.query(query_embeddings=query_embedding, n_results=n_fetch, include=["documents", "metadatas", "distances"])
    # docs = results["documents"][0]
    # metas = results["metadatas"][0]
    distances = results["distances"][0]
    ids = results["ids"][0]

    relevance_vector = [1.0 / (1.0 + d) for d in distances]

    top_bm25 = sorted(range(len(query_bm25)), key=lambda i: query_bm25[i], reverse=True)[:n_fetch]
    top_bm25_scores = [query_bm25[i] for i in top_bm25]
    bm25_ids = [ordered_ids[i] for i in top_bm25]

    if top_bm25:
        max_s = max(top_bm25_scores)
        min_s = min(top_bm25_scores)
        if max_s == min_s:
            relavance_bm25 = [1.0] * len(top_bm25)
        else:
            distance_bm25 = [(max_s - s) / (max_s - min_s) * 2.0 for s in top_bm25]
            relavance_bm25 = [1.0 / (1.0 + d) for d in distance_bm25]
    else:
        bm25_ids, relavance_bm25 = [], []
    
    all_candidate_ids = set(ids) | set(bm25_ids)
    importance = {}
    for cid in all_candidate_ids:
        _, meta = id_to_doc_meta[cid]
        importance[cid] = meta.get("importance", 3) / 5.0

    combined = {}
    for cid, score in zip(ids, relevance_vector):
        combined[cid] = combined.get(cid, 0) + vector_relevance_importance_weight * score
    for cid, score in zip(bm25_ids, relavance_bm25):
        combined[cid] = combined.get(cid, 0) + (rank_relevance_importance_weight) * score
    for cid in all_candidate_ids:
        combined[cid] = combined.get(cid, 0) + manual_rank_importance_weight * importance[cid]

    sorted_indices = sorted(combined, key=combined.get, reverse=True)
    top_ids = sorted_indices[:n_keep]
    top_docs = [id_to_doc_meta[idx][0] for idx in top_ids]
    # seen_types = set()
    # deduped = []
    # for idx in sorted_indices:
    #     doc, meta = id_to_doc_meta[idx]
    #     chunk_type = meta.get("type", "unknown")
    #     if chunk_type not in seen_types:
    #         seen_types.add(chunk_type)
    #         deduped.append(doc)
    #     if len(deduped) == n_keep:
    #         break

    return "\n\n---\n\n".join(top_docs)

def is_hallucinating(response: str) -> bool:
    lower = response.lower()
    return any(signal in lower for signal in HALLUCINATION_SIGNALS)

def ask_llm(system: str, user: str) -> str:
    result = ollama.chat(
        model="gemma2:2b",
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        options={"temperature": 0.3, "num_predict": 500, "num_ctx": 2048},
    )
    print(f"[Ollama stats] total={result['total_duration']/1e9:.1f}s, "
          f"prompt_eval={result['prompt_eval_duration']/1e9:.2f}s, "
          f"eval={result['eval_duration']/1e9:.2f}s, "
          f"tokens={result['eval_count']}")
    return result["message"]["content"].strip()

# ---------- Realistic Recruiter Questions ----------
questions = [
    # Generic Test Questions
    # "why should I hire him?",
    # "What is Sherriff's current availability and what types of roles is he open to?",
    # "Can you give me a quick summary of his strongest technical skills?",
    # "What has he actually built—walk me through a couple of his key projects.",
    # "What cloud and DevOps experience does he have? I want to know which platforms and CI/CD tools he’s used in practice.",
    # "I see a short stint at Cashco Financial. Why did that end, and did he still get anything out of it?",
    # "What makes him different from other DevOps or AI candidates I might be talking to?",

    # Specific Job Test Questions
    "Can you describe a specific project where you used AI coding agents like Claude Code, Cursor, or Copilot as your primary development accelerator?",
    "How do you typically prompt, steer, and review AI-generated code to ensure correctness, security, and maintainability?",
    "What full-stack applications have you built using React (or a similar frontend framework) and Django (or a similar backend framework with an ORM)?",
    "Walk us through your experience with Django ORM: how do you approach designing models, writing migrations, and optimizing querysets?",
    "This role requires in-person work in Calgary, AB. Are you currently located in Calgary or willing to relocate to the T2C 3G3 area?",
    "The posted salary range is 50,000–80,000 CAD per year. Does that align with your expectations?",
    "Describe a time you integrated an AI/ML model into a production application. What challenges did you face?",
    "Which agentic development tools have you adopted most recently, and how do you evaluate new ones before integrating them into your workflow?",
    "How would you explain RESTful API design to a junior developer? Give an example of a well-designed endpoint from your past work.",
    "Have you used Docker, Kubernetes, or any cloud platform (AWS, Azure, GCP) to deploy or maintain services? Please elaborate.",
    "Do you have experience deploying or fine-tuning open-source LLMs like Llama or using tools like vLLM or Ollama?",
    "What’s your approach to writing clean, well-tested, and documented code when collaborating under tight delivery timelines?",
    "Have you contributed to open-source projects or built a public GitHub portfolio? If so, please share a link or highlight.",
    "In your view, what separates a developer who simply uses AI tools from one who is truly AI-forward and agentic?"
]

print("Running automatic question set ...\n")
for q in questions:
    print(f"\n> {q}")
    t0 = time.time()
    normalized = normalize_query(q)
    q_bm25 = bm25.get_scores(re.findall(r'\w+', normalized.lower()))
    q_emb = embedder.encode([normalized], convert_to_tensor=False).tolist()
    t1 = time.time()

    context = retrieve_context(q_bm25, q_emb)
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







# import time
# import torch
# import ollama
# import chromadb
# from sentence_transformers import SentenceTransformer

# device = "cuda" if torch.cuda.is_available() else "cpu"
# embedder = SentenceTransformer("all-mpnet-base-v2").to(device)

# client = chromadb.PersistentClient(path="./my_vectordb")
# collection = client.get_collection("my_chunks")

# SYSTEM_PROMPT = (
#     "You are Sherriff Kadiri's portfolio assistant. "
#     "Use ONLY the context below to answer. "
#     "If the answer isn't in the context, say exactly: "
#     "'I don't have that detail — contact Sherriff.kadiri@outlook.com or visit https://github.com/KingSherriff.' "
#     "Keep responses under 4 sentences. Never mention you are an AI."
# )

# HALLUCINATION_SIGNALS = [
#     "as an ai", "i don't have personal", "i cannot", "i'm not able to",
#     "as a language model", "developed by", "my training", "i don't possess",
#     "i am an ai", "i was created by", "i don't have access",
# ]

# FALLBACK = (
#     "I don't have enough detail in Sherriff's portfolio to answer that confidently. "
#     "Feel free to reach out at Sherriff.kadiri@outlook.com or visit "
#     "https://github.com/KingSherriff."
# )

# def normalize_query(raw: str) -> str:
#     lower = raw.lower().strip()
#     replacements = {
#         "does he":      "does Sherriff Kadiri",
#         "is he":        "is Sherriff Kadiri",
#         "has he":       "has Sherriff Kadiri",
#         "can he":       "can Sherriff Kadiri",
#         "did he":       "did Sherriff Kadiri",
#         "his ":         "Sherriff Kadiri's ",
#         "he ":          "Sherriff Kadiri ",
#         "how many years": "how many years of experience does Sherriff Kadiri have",
#     }
#     for k, v in replacements.items():
#         lower = lower.replace(k, v)
#     return lower

# def retrieve_context(query_embedding: list, n_fetch=5, n_keep=3) -> str:
#     importance_weight = 0.3
#     results = collection.query(query_embeddings=query_embedding, n_results=n_fetch, include=["documents", "metadatas", "distances"])
#     docs = results["documents"][0]
#     metas = results["metadatas"][0]
#     distances = results["distances"][0]

#     relevance = [1.0 / (1.0 + d) for d in distances]
#     importance = [meta.get("importance", 3) / 5.0 for meta in metas]

#     combined_scores = [
#         (1 - importance_weight) * rel + importance_weight * imp
#         for rel, imp in zip(relevance, importance)
#     ]

#     sorted_indices = sorted(range(len(combined_scores)), key=lambda i: combined_scores[i], reverse=True)

#     seen_types = {}
#     deduped = []
#     for idx in sorted_indices:
#         chunk_type = metas[idx].get("type", "unknown")
#         if chunk_type not in seen_types:
#             seen_types[chunk_type] = True
#             deduped.append(docs[idx])
#         if len(deduped) == n_keep:
#             break

#     return "\n\n---\n\n".join(deduped)

# def is_hallucinating(response: str) -> bool:
#     lower = response.lower()
#     return any(signal in lower for signal in HALLUCINATION_SIGNALS)

# def ask_llm(system: str, user: str) -> str:
#     result = ollama.chat(
#         model="gemma2:2b",
#         messages=[{"role": "system", "content": system},
#                   {"role": "user", "content": user}],
#         options={"temperature": 0.3, "num_predict": 200, "num_ctx": 1024},
#     )
#     print(f"[Ollama stats] total={result['total_duration']/1e9:.1f}s, "
#           f"prompt_eval={result['prompt_eval_duration']/1e9:.2f}s, "
#           f"eval={result['eval_duration']/1e9:.2f}s, "
#           f"tokens={result['eval_count']}")
#     return result["message"]["content"].strip()

# # ---------- Realistic Recruiter Questions ----------
# questions = [
#     "Can you describe a specific project where you used AI coding agents like Claude Code, Cursor, or Copilot as your primary development accelerator?",
#     "How do you typically prompt, steer, and review AI-generated code to ensure correctness, security, and maintainability?",
#     "What full-stack applications have you built using React (or a similar frontend framework) and Django (or a similar backend framework with an ORM)?",
#     "Walk us through your experience with Django ORM: how do you approach designing models, writing migrations, and optimizing querysets?",
#     "This role requires in-person work in Calgary, AB. Are you currently located in Calgary or willing to relocate to the T2C 3G3 area?",
#     "The posted salary range is 50,000–80,000 CAD per year. Does that align with your expectations?",
#     "Describe a time you integrated an AI/ML model into a production application. What challenges did you face?",
#     "Which agentic development tools have you adopted most recently, and how do you evaluate new ones before integrating them into your workflow?",
#     "How would you explain RESTful API design to a junior developer? Give an example of a well-designed endpoint from your past work.",
#     "Have you used Docker, Kubernetes, or any cloud platform (AWS, Azure, GCP) to deploy or maintain services? Please elaborate.",
#     "Do you have experience deploying or fine-tuning open-source LLMs like Llama or using tools like vLLM or Ollama?",
#     "What’s your approach to writing clean, well-tested, and documented code when collaborating under tight delivery timelines?",
#     "Have you contributed to open-source projects or built a public GitHub portfolio? If so, please share a link or highlight.",
#     "In your view, what separates a developer who simply uses AI tools from one who is truly AI-forward and agentic?"
# ]

# print("Running automatic question set ...\n")
# for q in questions:
#     print(f"\n> {q}")
#     t0 = time.time()
#     normalized = normalize_query(q)
#     q_emb = embedder.encode([normalized], convert_to_tensor=False).tolist()
#     t1 = time.time()

#     context = retrieve_context(q_emb)
#     t2 = time.time()

#     user_message = f"""Question: {q}

# Context from Sherriff's portfolio:
# ---
# {context}
# ---

# Answer the question using only the context above."""

#     answer = ask_llm(SYSTEM_PROMPT, user_message)
#     t3 = time.time()

#     if is_hallucinating(answer):
#         answer = FALLBACK

#     print(f"Assistant: {answer}")
#     print(f"[Timings] Embed: {t1-t0:.2f}s | Retrieve: {t2-t1:.3f}s | LLM: {t3-t2:.2f}s")

# print("\nAll questions answered.")