# import os
import json
import re

import torch
import ollama
import pickle
import chromadb
from sentence_transformers import SentenceTransformer
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import *
from dotenv import load_dotenv

load_dotenv()
# HF_TOKEN = os.getenv("HF_TOKEN")
device = "cuda" if torch.cuda.is_available() else "cpu"
embedder = SentenceTransformer("all-mpnet-base-v2").to(device)

client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
collection = client.get_collection(COLLECTION_NAME)

all_data = collection.get(include=["documents", "metadatas"])
id_to_doc_meta = {all_data["ids"][i]: (all_data["documents"][i], all_data["metadatas"][i]) for i in range(len(all_data["ids"]))}
ordered_ids = list(id_to_doc_meta.keys())

with open('bm25_model.pkl', 'rb') as f:
    bm25 = pickle.load(f)

def normalize_query(raw: str) -> str:
    lower = raw.lower().strip()
    replacements = {"does he": "does {CANDIDATE_NAME}", "is he": "is {CANDIDATE_NAME}", "has he": "has {CANDIDATE_NAME}", "can he": "can {CANDIDATE_NAME}", "did he": "did {CANDIDATE_NAME}", "his ": "{CANDIDATE_NAME}'s ", "he ": "{CANDIDATE_NAME} ", "how many years": "how many years of experience does {CANDIDATE_NAME} have"}
    for k, v in replacements.items():
        lower = lower.replace(k, v)
    return lower

def multi_query_split(raw: str) -> str:
    query = normalize_query(raw)
    answer = ask_llm(MULTI_QUERY_SPLIT_PROMPT, f"Original User Question: {query}\nCandidate's name: {CANDIDATE_NAME}", 400, 1024, {"type": "array", "items": {"type": "string"}})
    # print(answer)
    return answer

def multi_query_embed(questions) -> list:
    normalized = [normalize_query(q) for q in questions]
    q_embs = embedder.encode(normalized, convert_to_tensor=False).tolist()
    with ThreadPoolExecutor(max_workers=len(q_embs)) as executor:
        futures = [executor.submit(retrieve_context, q_emb, normalized[i]) for i, q_emb in enumerate(q_embs)]
        return [future.result() for future in as_completed(futures)]

def reciprocal_rank_fusion(results, k=60):
    scores = {}
    for result in results:
        for rank, chunk_id in enumerate(result, start=1):
            if chunk_id not in scores:
                scores[chunk_id] = 0
            scores[chunk_id] += 1 / (k + rank)
    sorted_chunks = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    # print(sorted_chunks)
    return [chunk_id for chunk_id, score in sorted_chunks]
    

def retrieve_context(query_embedding: list, raw: str, n_fetch: int = 5, n_keep: int = 3) -> str:
    tokenized = re.findall(r'\w+', raw.lower())
    bm25_scores = bm25.get_scores(tokenized)
    top_bm25 = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:n_fetch]
    bm25_ids = [ordered_ids[i] for i in top_bm25]
    vector_results = collection.query(query_embeddings=query_embedding, n_results=n_fetch)
    vector_ids = vector_results["ids"][0]
    combined_ids = list(dict.fromkeys(bm25_ids + vector_ids))
    return combined_ids

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

def generate_final_answer(question: str, fused: list, top_k: int = 6) -> str:
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
    answer = ask_llm(system_prompt, user_prompt, num_pred=1500, num_ctx=8192)
    return answer

def run_chat():
    print("RAG Chatbot ready")

    while True:
        question = input("\n> ").strip()
        if not question or question.lower() in ["exit", "quit"]:
            break
        # normalized = normalize_query(question)
        # q_emb = embedder.encode([normalized], convert_to_tensor=False).tolist()
        # context = retrieve_context(q_emb)
        # user_message = QUESTION.format(question = question, context = context)

        # answer = ask_llm(SYSTEM_PROMPT, user_message)
        questions = json.loads(multi_query_split(question))
        questions = [question] + questions
        raw_answer = multi_query_embed(questions)
        ranked_results = reciprocal_rank_fusion(raw_answer)
        answer = generate_final_answer(question, ranked_results)
        if is_hallucinating(answer):
            answer = FALLBACK
        print(f"\nAssistant: {answer}")

run_chat()