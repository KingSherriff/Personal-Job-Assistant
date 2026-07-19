import re
import json
import ollama
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

log = logging.getLogger(__name__)

def normalize_query(raw, state) -> str:
    lower = raw.lower().strip()
    for k, v in state["config"]["PRONOUNS"].items():
        lower = re.sub(rf"\b(?:{k})\b", lambda m, r=v: r, lower, flags=re.IGNORECASE)
    return lower

def multi_query_split(raw, state) -> str:
    query = normalize_query(raw, state)
    answer = ask_llm(state["config"]["MULTI_QUERY_SPLIT_PROMPT"], f"Original User Question: {query}\nCandidate's name: {state['config']['CANDIDATE_NAME']}", 500, 8192, state, {"type": "array", "items": {"type": "string"}})
    return answer

def multi_query_embed(questions, state) -> list:
    normalized = [normalize_query(q, state) for q in questions]
    q_embs = state["embedder"].encode(normalized, prompt_name="query", convert_to_tensor=False).tolist()
    ranked = []
    with ThreadPoolExecutor(max_workers=len(q_embs)) as executor:
        futures = [executor.submit(retrieve_context, q_emb, normalized[i], state) for i, q_emb in enumerate(q_embs)]
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
    return [chunk_id for chunk_id, _ in sorted_chunks]
    

def retrieve_context(query_embedding: list, raw: str, state) -> list:
    n_fetch = 5
    tokenized = re.findall(r'\w+', raw.lower())
    bm25_scores = state["bm25"].get_scores(tokenized)
    if max(bm25_scores, default=0) < float(state["config"]["BM25_MIN_SCORE"]):
        bm25_ids = []
    else:
        top_bm25 = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:n_fetch]
        bm25_ids = [state["bm25_ids_ordered"][i] for i in top_bm25]
    vector_ids = state["collection"].query(query_embeddings=[query_embedding], n_results=n_fetch)["ids"][0]
    return [bm25_ids, vector_ids]

def is_hallucinating(response, state) -> bool:
    lower = response.lower()
    soft = [s for s in state["config"]["SOFT_SIGNALS"] if s in lower]
    if soft:
        log.warning("soft signal %s in answer: %.200s", soft, response)
    return any(s in lower for s in state["config"]["PERSONA_BREAKS"])

def ask_llm(system, user, num_pred, num_ctx, state, format_schema=None) -> str:
    options = {"temperature": 0.3, "num_predict": num_pred, "num_ctx": num_ctx}
    kwargs = {"format": format_schema} if format_schema is not None else {}
    result = ollama.chat(model=state["config"]["OLLAMA_MODEL"], messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], options=options, think=False, **kwargs)
    if result.get("done_reason") == "length":
        log.warning("hit num_predict=%s — output truncated", num_pred)
    return result["message"]["content"].strip()

def generate_final_answer(question, fused, state, top_k = 5) -> str:
    top_ids = fused[:top_k]
    top = []
    for chunk in top_ids:
        if chunk in state["id_to_doc_meta"]:
            doc, _ = state["id_to_doc_meta"][chunk]
            top.append(doc)
        else:
            result = state["collection"].get(ids=[chunk])
            if result["documents"]:
                top.append(result["documents"][0])

    context = "\n\n---\n\n".join(top)
    user_prompt = state["config"]["QUESTION"].format(question=question, context=context, candidate_name=state["config"]["CANDIDATE_NAME"])
    answer = ask_llm(state["config"]["SYSTEM_PROMPT"], user_prompt, num_pred=500, num_ctx=8192, state=state)
    return answer

def get_answer(question, state) -> str:
    try:
        parsed = json.loads(multi_query_split(question, state))
        variants = parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        variants = []
    questions = [question] + [q for q in variants if isinstance(q, str)]
    raw_answer = multi_query_embed(questions, state)
    ranked_results = reciprocal_rank_fusion(raw_answer)
    answer = generate_final_answer(question, ranked_results, state)
    if not answer or is_hallucinating(answer, state):
        answer = state["config"]["FALLBACK"]
    return answer