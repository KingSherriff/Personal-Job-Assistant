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
    .run_commands("curl -fsSL https://ollama.com/install.sh | sh", f"ollama serve & SERVE_PID=$!; for i in $(seq 1 60); do ollama list >/dev/null 2>&1 && break; sleep 1; done; ollama pull {MODEL_TAG}; RC=$?; kill $SERVE_PID 2>/dev/null || true; exit $RC").pip_install("fastapi[standard]", "sentence-transformers>=5.0", "chromadb", "rank-bm25", "ollama", "pydantic",)
    .run_commands(f"python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('{EMBED_TAG}')\"")
    .add_local_python_source("config", "rag_core")
)

volume = modal.Volume.from_name("rag-data", create_if_missing=True)
secret = modal.Secret.from_name("rag-config")
app = modal.App("rag-chatbot")
with image.imports():
    import os
    import pickle
    import shutil
    import subprocess
    import time

    import chromadb
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    from sentence_transformers import SentenceTransformer

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
        OLLAMA_MODEL
    )
    from rag_core import get_answer

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
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"Embedding {len(contents)} chunks with {EMBEDDING_MODEL}")
    embeddings = model.encode(contents, convert_to_tensor=False).tolist()
    B = 1000
    for i in range(0, len(ids), B):
        collection.add(ids=ids[i : i + B], documents=contents[i : i + B], embeddings=embeddings[i : i + B], metadatas=metadatas[i : i + B])

    tokenized = [re.findall(r"\w+", doc.lower()) for doc in contents]
    bm25 = rank_bm25.BM25Okapi(tokenized)
    with open(BM25_PATH, "wb") as f:
        pickle.dump({"bm25": bm25, "ids": ids, "embedding_model": EMBEDDING_MODEL}, f)
    volume.commit()
    print(f"Indexed {len(ids)} chunks.")


def build_state():
    """Load everything once per container, at cold start."""
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

    warm = threading.Thread(target=lambda: ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": "warmup"}], options={"num_ctx": 8192, "num_predict": 1}, think=False), daemon=True)
    warm.start()
    volume.reload()

    with open(BM25_PATH, "rb") as f:
        bm25_pkg = pickle.load(f)

    indexed_with = bm25_pkg.get("embedding_model")
    if indexed_with and indexed_with != EMBEDDING_MODEL:
        raise RuntimeError(f"Index was built with {indexed_with!r} but serving with " f"{EMBEDDING_MODEL!r}. Re-run the index function.")

    if EMBEDDING_MODEL != EMBED_TAG:
        raise RuntimeError(
            f"EMBEDDING_MODEL={EMBEDDING_MODEL!r} differs from the baked "
            f"EMBED_TAG={EMBED_TAG!r}; the cached weights won't be used."
        )
    embedder = SentenceTransformer(EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection(COLLECTION_NAME)

    all_data = collection.get(include=["documents", "metadatas"])
    id_to_doc_meta = {
        all_data["ids"][i]: (all_data["documents"][i], all_data["metadatas"][i])
        for i in range(len(all_data["ids"]))
    }

    warm.join()
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
            "EMBEDDING_MODEL": EMBEDDING_MODEL
        },
    }

@app.function(
    image=image,
    volumes={VOLUME_PATH: volume},
    secrets=[secret],
    gpu="T4",
    min_containers=0,
    max_containers=1,
    scaledown_window=60,
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
        return {"answer": get_answer(request.question, state)}

    return web_app