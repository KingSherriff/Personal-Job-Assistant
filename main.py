from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import os
import torch
import json
import chromadb

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

with open("data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

device = "cuda" if torch.cuda.is_available() else "cpu"
model = SentenceTransformer("all-mpnet-base-v2").to(device)
# model = SentenceTransformer("google/embeddinggemma-300M", token=HF_TOKEN).to(device)
client = chromadb.PersistentClient(path="./my_vectordb")

try:
    client.delete_collection("my_chunks")
except:
    pass


collection = client.create_collection("my_chunks")
contents = [item["content"] for item in data]
metadatas = [sanitize_metadata(item["metadata"]) for item in data]
ids = [f"{item['metadata']['chunk_id']}_{i}" for i, item in enumerate(data)]
print(f"Generating {len(contents)} embeddings")
embeddings = model.encode(contents, convert_to_tensor=False).tolist()
collection.add(
    ids=ids,
    documents=contents,
    embeddings=embeddings,
    metadatas=metadatas
)

print(f"Added {len(ids)} chunks.")