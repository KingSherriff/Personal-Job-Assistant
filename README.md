# Portfolio Assistant RAG Chatbot

A retrieval‑augmented generation chatbot that answers recruiter questions about my background with high factual accuracy.
Built with ChromaDB, SentenceTransformers, and a local Gemma 2B LLM via Ollama.

## Overview

Recruiters ask predictable but critical questions: *“What are your strongest skills?”*, *“What have you built?”*, *“Why the short tenure at X?”*.  
A static portfolio can’t answer these instantly, and a generic chatbot would hallucinate.  
This **RAG pipeline** grounds every answer **exclusively in my curated portfolio chunks**, ensuring responses are accurate, on‑brand, and available 24/7.

The system:
- Embeds and stores my professional background in a vector database.
- Retrieves the most relevant chunks for a given question.
- Feeds them to a local LLM with strict instructions to avoid hallucination.
- Evaluates its own answers with faithfulness, relevance, completeness, and accuracy metrics.

## Motivation

I built this project to:
- Demonstrate **end‑to‑end RAG engineering** – from chunking to evaluation.
- Create a **trustworthy personal assistant** that can represent me accurately when I’m not available.
- Experiment with **retrieval strategies, prompt engineering, and hallucination prevention** in a real‑world, high‑stakes domain (job search).
- Iteratively improve an AI system using rigorous, evidence‑based evaluation.

# How It Works

## RAG Pipeline Details

### 1. Document Chunking & Embedding
My portfolio content (work history, projects, skills, FAQ, bio, contact info) is divided into **semantic chunks** – each representing a coherent unit like a single project, a skill category, or a Q&A pair.  
Each chunk is embedded using **`all‑mpnet‑base‑v2`** (SentenceTransformers), which produces a 768‑dimension dense vector. Embeddings are computed on GPU if available, and stored alongside metadata (chunk type, importance, tags, date, etc.) in a persistent **ChromaDB** collection.

**Chunk metadata fields:**  
- `chunk_id`, `type` (work, project, skill, bio, faq, summary, system_instruction)  
- `importance` (1–5, used for optional weighted retrieval)  
- `tags` (for future keyword‑augmented retrieval)  
- `title`, `company`, `role`, `date_start`, `date_end`, etc.

### 2. Query Normalization
User input often contains pronouns (“his”, “he”, “does he”) that can confuse retrieval. A simple rule‑based normalizer rewrites the query to include the full name `Sherriff Kadiri` and expands common shorthand:
- `does he` → `does Sherriff Kadiri`
- `his` → `Sherriff Kadiri's`
- `he` → `Sherriff Kadiri`
- `how many years` → `how many years of experience does Sherriff Kadiri have`

This consistently improves embedding similarity to the target chunks.

### 3. Retrieval Strategy
The normalized query is embedded and used to query the ChromaDB collection with **`n_fetch=5`** (top‑5 similarity results). Before passing to the LLM, results are **deduplicated by chunk type** – only the first occurrence of each `type` (e.g., `work`, `skill`, `project`, `bio`, `faq`) is kept, and a maximum of **`n_keep=3`** chunks are retained. This prevents a single dominating topic (like “projects”) from flooding the context and ensures the LLM sees a diverse set of relevant information.

**Importance scores** (metadata) can optionally bias retrieval, but the current implementation relies solely on embedding similarity and deduplication for simplicity and speed.

### 4. Generation & Prompt Engineering
The retrieved chunks are concatenated with the user question and a strict **system prompt**:

# Loop Pipeline Details

### 1. Chunking & Embedding
My resume, project descriptions, FAQs, and bio are split into semantic chunks. Each chunk is embedded using `all‑mpnet‑base‑v2` (SentenceTransformers) and stored in a persistent **ChromaDB** collection.

### 2. Query Normalization
To improve retrieval, ambiguous pronouns are rewritten – e.g., *“Why should I hire him?”* → *“Why should I hire Sherriff Kadiri?”*

### 3. Context Retrieval
The user’s query is embedded and used to fetch the top‑N most relevant chunks from ChromaDB.  
A **deduplication layer** ensures diverse context types (skills, projects, bio) are included, preventing single‑topic bias.

### 4. Grounded Generation
The retrieved context and a carefully crafted **system prompt** are sent to a local LLM (Gemma 2B) via Ollama. The prompt:
- Bans hallucination and forces answers to rely **only** on the provided context.
- Caps response length (typically ≤ 4 sentences).
- Enforces a third‑person assistant persona (never “I” as Sherriff).
- Provides a safe fallback message when the answer cannot be found.

### 5. Safety Net
A post‑generation filter scans for AI‑self‑disclosure patterns (e.g., *“as an AI”*) and automatically falls back to:
> “I don’t have enough detail in Sherriff’s portfolio to answer that confidently.  
> Feel free to reach out at Sherriff.kadiri@outlook.com or visit https://github.com/KingSherriff.”

## Evaluation & Results
*Key improvements:*  
- Added a **Project Portfolio Overview** chunk to ensure AI/ML projects are always mentioned.  
- Created a **Complete Cloud & DevOps Stack** chunk to eliminate missing platform details.  
- Reduced retrieval breadth (n_fetch=5, n_keep=3) to avoid context dilution and hallucinations. Reduced num_predict to 200 for consiceness and latency.
- Enforced third‑person answers after observing first‑person slips.

*Current focus:*  
- Boosting completeness for “target roles” and “project walkthrough” questions.  
- Reducing latency for interactive use.

## 🛠 Tech Stack

| Category          | Tools / Libraries |
|-------------------|-------------------|
| **Vector DB**     | ChromaDB          |
| **Embeddings**    | SentenceTransformers (`all‑mpnet‑base‑v2`) |
| **LLM**           | Ollama + Gemma 2B |
| **Language**      | Python 3.10+      |
| **Other**         | PyTorch, Hugging Face Hub |

## ⚙️ Setup & Usage

### Prerequisites
- Python 3.10+
- [Ollama](https://ollama.com/) installed and running with the `gemma2:2b` model pulled.
- Clone this repo and install dependencies:



```bash
git clone https://github.com/KingSherriff/portfolio-assistant-rag.git
cd portfolio-assistant-rag
pip install -r requirements.txt
```
Run the Assistant `python auto_question_runner.py`

This will automatically ask the 7 recruiter questions and print answers + timings.

For interactive mode, run:
`python chat.py`

## Configuration
- Retrieval depth: Adjust n_fetch and n_keep in retrieve_context().
- LLM model: Change the model name in ask_llm() (e.g., "phi:mini").
- System prompt: Modify SYSTEM_PROMPT to adjust tone/behaviour.

# Contact
Sherriff Kadiri
📧 Sherriff.kadiri@outlook.com
🔗 LinkedIn
🐙 GitHub

If you have any questions about this project or want to discuss RAG/LLM engineering, feel free to reach out!
