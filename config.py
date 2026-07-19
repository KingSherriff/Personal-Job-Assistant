import os
from dotenv import load_dotenv

load_dotenv()

CANDIDATE_NAME = os.getenv("CANDIDATE_NAME", "the candidate")
CANDIDATE_EMAIL = os.getenv("CANDIDATE_EMAIL", "test@gmail.com")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./my_vectordb")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-mpnet-base-v2")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "my_chunks")
GITHUB_LINK = os.getenv("GITHUB_LINK", "https://github.com")

SYSTEM_PROMPT = (
    f"You are {CANDIDATE_NAME}'s portfolio assistant. "
    "Use ONLY the context below to answer. "
    "If the answer isn't in the context, say exactly: "
    f"'I don't have that detail — contact {CANDIDATE_EMAIL} or visit {GITHUB_LINK}.' "
    "Keep responses under 4 sentences. Never mention you are an AI."
)

MULTI_QUERY_SPLIT_PROMPT = (
    """You are a search query rewriter for a recruitment-oriented personal assistant. 
    Your sole task is to generate exactly 3 distinct search queries from completely different angles based on the user's original question to maximize retrieval recall from a candidate's professional knowledge base.

    **CRITICAL CONSTRAINT:** 
    All generated queries MUST explicitly reference the individual candidate (use 'the candidate' or 'this person'). 
    This ensures the retriever fetches documents about THIS specific person, not general industry knowledge. 

    **Strategies to apply across the 3 queries (apply one per query, prioritize Rule 4 if applicable):**

    1. **Formal Recruiter Rephrase:** Convert casual language into formal HR terminology.
    2. **Decomposition:** If the question combines multiple topics, break it into the single most critical atomic sub-topic.
    3. **Acronym & Synonym Expansion:** Expand technical jargon, acronyms, and alternative job titles.
    4. **Comparative/Contrastive (PRIORITY):** If the original question contains 'or', 'versus', or implies a binary choice, ensure at least one query explicitly asks for the primary role or dominant focus.

    **Output Rules:**
    - Output **ONLY** a valid JSON array of 3 strings. No explanations, no bullet points, no markdown.
    - Queries must be between 5 and 15 words long.
    - Do NOT generate questions (ending with '?'). Generate declarative search statements."""
)

FALLBACK = (
    f"I don't have enough detail in {CANDIDATE_NAME}'s portfolio to answer that confidently. "
    f"Feel free to reach out at {CANDIDATE_EMAIL} or visit "
    f"{GITHUB_LINK}."
)

QUESTION = (
    """Question: {question}
    Context from {candidate_name}'s portfolio:
    ---
    {context}
    ---
    Answer the question using only the context above."""
)

HALLUCINATION_SIGNALS = [
    "as an ai",
    "i don't have personal",
    "i cannot",
    "i'm not able to",
    "as a language model",
    "developed by",
    "my training",
    "i don't possess",
    "i am an ai",
    "i was created by",
    "i don't have access",
]