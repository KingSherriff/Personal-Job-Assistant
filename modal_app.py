import modal

VOLUME_PATH = "/data"
CHROMA_PATH = f"{VOLUME_PATH}/chroma"
BM25_PATH = f"{VOLUME_PATH}/bm25_model.pkl"
SOURCE_JSON = f"{VOLUME_PATH}/data.json"

MODEL_TAG = "qwen3:8b"
EMBED_TAG = "Qwen/Qwen3-Embedding-0.6B"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("curl", "procps", "zstd", "ca-certificates", "tar")
    .run_commands("curl -fsSL https://ollama.com/install.sh | sh",f"ollama serve & SERVE_PID=$!; for i in $(seq 1 60); do ollama list >/dev/null 2>&1 && break; sleep 1; done; ollama pull {MODEL_TAG}; RC=$?; kill $SERVE_PID 2>/dev/null || true; exit $RC",)
    .pip_install("fastapi[standard]","sentence-transformers>=5.0","chromadb","rank-bm25","ollama","pydantic",)
    .env({"HF_HUB_OFFLINE": "1","TRANSFORMERS_OFFLINE": "1","HF_HUB_DISABLE_TELEMETRY": "1",})
    .run_commands(f"python -c \"from sentence_transformers import SentenceTransformer; "f"m = SentenceTransformer('{EMBED_TAG}', device='cuda'); "f"m.encode(['warmup'])\"",gpu="T4",)
    .run_commands("ollama serve & for i in $(seq 1 60); do ollama list >/dev/null 2>&1 && break; sleep 1; done; ""curl -s http://127.0.0.1:11434/api/chat -d ""'{\"model\":\"" + MODEL_TAG + "\",""\"messages\":[{\"role\":\"user\",\"content\":\"warmup\"}],""\"options\":{\"num_ctx\":8192,\"num_predict\":16},""\"think\":false,\"stream\":false}' >/dev/null",gpu="T4",)
    .add_local_python_source("config", "rag_core")
)

volume = modal.Volume.from_name("rag-data", create_if_missing=True)
secret = modal.Secret.from_name("rag-config")
app = modal.App("rag-chatbot")

with image.imports():
    import os

    # Set DEBUG_TIMING=1 in the rag-config secret to re-enable verbose
    # cold-start profiling if you ever need to re-diagnose a slowdown
    # (e.g. a driver update invalidating the baked CUDA JIT cache).
    _DEBUG_TIMING = os.environ.get("DEBUG_TIMING", "0") == "1"

    import pickle
    import shutil
    import subprocess
    import time as _time

    _t0 = _time.perf_counter()

    _t1 = _time.perf_counter()
    import torch
    if _DEBUG_TIMING:
        print(f"[timing] torch import: {_time.perf_counter()-_t1:.1f}s")

    _t2 = _time.perf_counter()
    import chromadb
    from chromadb.config import Settings
    if _DEBUG_TIMING:
        print(f"[timing] chromadb import: {_time.perf_counter()-_t2:.1f}s")

    _t3 = _time.perf_counter()
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    if _DEBUG_TIMING:
        print(f"[timing] fastapi/pydantic import: {_time.perf_counter()-_t3:.1f}s")

    _t4 = _time.perf_counter()
    from sentence_transformers import SentenceTransformer
    if _DEBUG_TIMING:
        print(f"[timing] sentence_transformers import: {_time.perf_counter()-_t4:.1f}s")

    from config import (
        BM25_MIN_SCORE,
        CANDIDATE_NAME,
        COLLECTION_NAME,
        EMBEDDING_MODEL,
        FALLBACK,
        PERSONA_BREAKS,
        SOFT_SIGNALS,
        MULTI_QUERY_SPLIT_PROMPT,
        PRONOUNS,
        QUESTION,
        SYSTEM_PROMPT,
        OLLAMA_MODEL,
    )
    from rag_core import get_answer

    if _DEBUG_TIMING:
        print(f"[timing] TOTAL top-level imports: {_time.perf_counter()-_t0:.1f}s")

    # module-level alias so build_state()/index() can use `time` as before
    time = _time

# reused everywhere a Chroma client is constructed, to kill the posthog
# telemetry call that can stall for several seconds on a fresh container
CHROMA_SETTINGS = Settings(anonymized_telemetry=False)


@app.function(
    image=image,
    volumes={VOLUME_PATH: volume},
    secrets=[secret],
    timeout=60 * 30,
)
def index():
    import json
    import re
    import rank_bm25

    with open(SOURCE_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    def sanitize(meta):
        clean = {}
        for key, value in meta.items():
            if isinstance(value, (str, int, float, bool)):
                clean[key] = value
            elif value is None:
                clean[key] = ""
            else:
                clean[key] = json.dumps(value, ensure_ascii=False)
        return clean

    contents = [item["content"] for item in data]
    metadatas = [sanitize(item["metadata"]) for item in data]
    ids = [f"{item['metadata']['chunk_id']}_{i}" for i, item in enumerate(data)]

    shutil.rmtree(CHROMA_PATH, ignore_errors=True)
    client = chromadb.PersistentClient(path=CHROMA_PATH, settings=CHROMA_SETTINGS)
    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"Embedding {len(contents)} chunks with {EMBEDDING_MODEL}")
    embeddings = model.encode(contents, convert_to_tensor=False).tolist()
    B = 1000
    for i in range(0, len(ids), B):
        collection.add(
            ids=ids[i : i + B],
            documents=contents[i : i + B],
            embeddings=embeddings[i : i + B],
            metadatas=metadatas[i : i + B],
        )

    tokenized = [re.findall(r"\w+", doc.lower()) for doc in contents]
    bm25 = rank_bm25.BM25Okapi(tokenized)
    with open(BM25_PATH, "wb") as f:
        pickle.dump({"bm25": bm25, "ids": ids, "embedding_model": EMBEDDING_MODEL}, f)
    volume.commit()
    print(f"Indexed {len(ids)} chunks.")


def build_state():
    t0 = time.perf_counter()
    env = os.environ.copy()
    env.setdefault("OLLAMA_HOST", "127.0.0.1:11434")
    env.setdefault("OLLAMA_KEEP_ALIVE", "-1")
    subprocess.Popen(["ollama", "serve"], env=env)
    import ollama
    import threading

    for _ in range(60):
        try:
            ollama.list()
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("ollama did not become ready within 60s")
    if _DEBUG_TIMING:
        print(f"[timing] ollama ready: {time.perf_counter()-t0:.1f}s")

    def timed_warm():
        tw = time.perf_counter()
        ollama.chat(model=OLLAMA_MODEL,messages=[{"role": "user", "content": "warmup"}],options={"num_ctx": 8192, "num_predict": 1},think=False,)
        if _DEBUG_TIMING:
            print(f"[timing] ollama warmup: {time.perf_counter()-tw:.1f}s")

    warm = threading.Thread(target=timed_warm, daemon=True)
    warm.start()

    tv = time.perf_counter()
    volume.reload()
    if _DEBUG_TIMING:
        print(f"[timing] volume.reload: {time.perf_counter()-tv:.1f}s")

    tb = time.perf_counter()
    with open(BM25_PATH, "rb") as f:
        bm25_pkg = pickle.load(f)
    if _DEBUG_TIMING:
        print(f"[timing] bm25 pickle load: {time.perf_counter()-tb:.1f}s")

    indexed_with = bm25_pkg.get("embedding_model")
    if indexed_with and indexed_with != EMBEDDING_MODEL:
        raise RuntimeError(f"Index was built with {indexed_with!r} but serving with "f"{EMBEDDING_MODEL!r}. Re-run the index function.")

    if EMBEDDING_MODEL != EMBED_TAG:
        raise RuntimeError(f"EMBEDDING_MODEL={EMBEDDING_MODEL!r} differs from the baked "f"EMBED_TAG={EMBED_TAG!r}; the cached weights won't be used.")

    te = time.perf_counter()
    embedder = SentenceTransformer(EMBEDDING_MODEL)
    if _DEBUG_TIMING:
        print(f"[timing] embedder init: {time.perf_counter()-te:.1f}s")

    tc = time.perf_counter()
    client = chromadb.PersistentClient(path=CHROMA_PATH, settings=CHROMA_SETTINGS)
    collection = client.get_collection(COLLECTION_NAME)
    all_data = collection.get(include=["documents", "metadatas"])
    if _DEBUG_TIMING:
        print(f"[timing] chroma load ({len(all_data['ids'])} docs): {time.perf_counter()-tc:.1f}s")

    id_to_doc_meta = {
        all_data["ids"][i]: (all_data["documents"][i], all_data["metadatas"][i])
        for i in range(len(all_data["ids"]))
    }

    warm.join()
    if _DEBUG_TIMING:
        print(f"[timing] TOTAL build_state: {time.perf_counter()-t0:.1f}s")
    return {
        "embedder": embedder,
        "collection": collection,
        "bm25": bm25_pkg["bm25"],
        "bm25_ids_ordered": bm25_pkg["ids"],
        "id_to_doc_meta": id_to_doc_meta,
        "config": {
            "PRONOUNS": PRONOUNS,
            "MULTI_QUERY_SPLIT_PROMPT": MULTI_QUERY_SPLIT_PROMPT,
            "CANDIDATE_NAME": CANDIDATE_NAME,
            "BM25_MIN_SCORE": float(BM25_MIN_SCORE),
            "QUESTION": QUESTION,
            "SYSTEM_PROMPT": SYSTEM_PROMPT,
            "PERSONA_BREAKS": PERSONA_BREAKS,
            "SOFT_SIGNALS": SOFT_SIGNALS,
            "FALLBACK": FALLBACK,
            "OLLAMA_MODEL": OLLAMA_MODEL,
            "EMBEDDING_MODEL": EMBEDDING_MODEL,
        },
    }


@app.function(
    image=image,
    volumes={VOLUME_PATH: volume},
    secrets=[secret],
    gpu="T4",
    min_containers=0,
    max_containers=1,
    scaledown_window=600,
    timeout=300,
    startup_timeout=600,
)
@modal.concurrent(max_inputs=4)
@modal.asgi_app()
def fastapi_app():
    web_app = FastAPI()

    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=[o for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o],
        allow_methods=["POST"],
        allow_headers=["Content-Type"],
    )

    class ChatRequest(BaseModel):
        question: str

    state = build_state()

    @web_app.get("/health")
    def health():
        return {"ok": True}

    @web_app.post("/discuss")
    def chat(request: ChatRequest):
        question = request.question.strip()
        if not question:
            return {"answer": state["config"]["FALLBACK"]}
        if len(question) > 500:
            return {"answer": "That's a bit long — mind shortening it?"}
        try:
            return {"answer": get_answer(question, state)}
        except Exception as e:
            print(f"[error] /discuss failed: {e!r}")
            return {"answer": state["config"]["FALLBACK"]}

    return web_app