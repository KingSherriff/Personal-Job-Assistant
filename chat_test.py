import re
import json
import torch
import ollama
import pickle
import chromadb
from config import *
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from sentence_transformers import SentenceTransformer, CrossEncoder

load_dotenv()
# HF_TOKEN = os.getenv("HF_TOKEN")
device = "cuda" if torch.cuda.is_available() else "cpu"
embedder = SentenceTransformer("all-mpnet-base-v2").to(device)
# encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", device=device)

client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
collection = client.get_collection(COLLECTION_NAME)

all_data = collection.get(include=["documents", "metadatas"])
id_to_doc_meta = {all_data["ids"][i]: (all_data["documents"][i], all_data["metadatas"][i]) for i in range(len(all_data["ids"]))}
ordered_ids = list(id_to_doc_meta.keys())



with open('bm25_model.pkl', 'rb') as f:
    _b = pickle.load(f)
bm25, bm25_ids_ordered = _b["bm25"], _b["ids"]

def normalize_query(raw: str) -> str:
    lower = raw.lower().strip()
    for k, v in PRONOUNS.items():
        lower = re.sub(rf"\b(?:{k})\b", lambda m, r=v: r, lower, flags=re.IGNORECASE)
    return lower

def multi_query_split(raw) -> str:
    query = normalize_query(raw)
    answer = ask_llm(MULTI_QUERY_SPLIT_PROMPT, f"Original User Question: {query}\nCandidate's name: {CANDIDATE_NAME}", 400, 1024, {"type": "array", "items": {"type": "string"}})
    print(answer)
    return answer

def multi_query_embed(questions) -> list:
    normalized = [normalize_query(q) for q in questions]
    q_embs = embedder.encode(normalized, convert_to_tensor=False).tolist()
    ranked = []
    with ThreadPoolExecutor(max_workers=len(q_embs)) as executor:
        futures = [executor.submit(retrieve_context, q_emb, normalized[i]) for i, q_emb in enumerate(q_embs)]
        for future in as_completed(futures):
            ranked.extend(future.result())
        return ranked

def reciprocal_rank_fusion(results, k=60):
    scores = {}
    for result in results:
        for rank, chunk_id in enumerate(result, start=1):
            if chunk_id not in scores:
                scores[chunk_id] = 0
            scores[chunk_id] += 1 / (k + rank)
    sorted_chunks = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    print(sorted_chunks)
    return [chunk_id for chunk_id, score in sorted_chunks]
    

def retrieve_context(query_embedding: list, raw: str, n_fetch: int = 5) -> str:
    tokenized = re.findall(r'\w+', raw.lower())
    bm25_scores = bm25.get_scores(tokenized)
    if max(bm25_scores) < float(BM25_MIN_SCORE):
        bm25_ids = []
    else:
        top_bm25 = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:n_fetch]
        bm25_ids = [bm25_ids_ordered[i] for i in top_bm25]
    vector_ids = collection.query(query_embeddings=[query_embedding], n_results=n_fetch)["ids"][0]
    return [bm25_ids, vector_ids]

def is_hallucinating(response: str) -> bool:
    lower = response.lower()
    return any(signal in lower for signal in HALLUCINATION_SIGNALS)

def ask_llm(system: str, user: str, num_pred: int, num_ctx: int, format_schema=None) -> str:
    options = {"temperature": 0.3, "num_predict": num_pred, "num_ctx": num_ctx}
    if format_schema is not None:
        result = ollama.chat(model="gemma2:2b", messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], format=format_schema, options=options)
    else:
        result = ollama.chat(model="gemma2:2b", messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], options=options)
    print(f"[Ollama stats] total={result['total_duration']/1e9:.1f}s prompt_eval={result['prompt_eval_duration']/1e9:.2f}s eval={result['eval_duration']/1e9:.2f}s, tokens={result['eval_count']}")
    return result["message"]["content"].strip()

def generate_final_answer(question: str, fused: list, top_k: int = 3) -> str:
    top_ids = fused[:top_k]
    top = []
    for chunk in top_ids:
        if chunk in id_to_doc_meta:
            doc, meta = id_to_doc_meta[chunk]
            top.append(doc)
        else:
            result = collection.get(ids=[chunk])
            if result["documents"]:
                top.append(result["documents"][0])

    context = "\n\n---\n\n".join(top)
    system_prompt = SYSTEM_PROMPT
    user_prompt = QUESTION.format(question=question, context=context, candidate_name=CANDIDATE_NAME)
    answer = ask_llm(system_prompt, user_prompt, num_pred=400, num_ctx=4096)
    return answer

def run_chat():
    print("RAG Chatbot ready")
 
    while True:
        question = input("\n> ").strip()
        if not question or question.lower() in ["exit", "quit"]:
            break
 
        if question.lower() in ("eval", "test", "run eval", "run tests"):
            from evaluate import run_eval_suite
            run_eval_suite()
            continue
 
        questions = [question]
        questions += multi_query_split(question)

        ranked_lists = multi_query_embed(questions)
        ranked_results = reciprocal_rank_fusion(ranked_lists)
        answer = generate_final_answer(question, ranked_results)
 
        if is_hallucinating(answer):
            answer = FALLBACK
        print(f"\nAssistant: {answer}")
 
 
if __name__ == "__main__":
    run_chat()