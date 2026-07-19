import re
import os
import json
import torch
import pickle
import chromadb
import rank_bm25
from config import *
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")

def sanitize_metadata(meta):
    clean = {}
    for key, value in meta.items():
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
        elif value is None:
            clean[key] = ""
        else:
            clean[key] = json.dumps(value, ensure_ascii=False)
    return clean

def keyword_rank(data):
    tokenized = [re.findall(r'\w+', doc.lower()) for doc in data]
    bm25 = rank_bm25.BM25Okapi(tokenized)
    with open('bm25_model.pkl', 'wb') as f:
        pickle.dump({"bm25": bm25, "ids": ids}, f)
    print("BM25 model saved")


with open("data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

device = "cuda" if torch.cuda.is_available() else "cpu"
model = SentenceTransformer(EMBEDDING_MODEL).to(device)
# model = SentenceTransformer("google/embeddinggemma-300M", token=HF_TOKEN).to(device)
client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

try:
    client.delete_collection(COLLECTION_NAME)
except:
    pass


collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
contents = [item["content"] for item in data]
metadatas = [sanitize_metadata(item["metadata"]) for item in data]
ids = [f"{item['metadata']['chunk_id']}_{i}" for i, item in enumerate(data)]
print(f"Generating {len(contents)} embeddings")
embeddings = model.encode(contents, convert_to_tensor=False).tolist()
collection.add(ids=ids, documents=contents, embeddings=embeddings, metadatas=metadatas)
keyword_rank(contents)
print(f"Added {len(ids)} chunks.")