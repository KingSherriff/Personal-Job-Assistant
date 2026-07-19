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
    "Be concise. Instead of abstract summaries, explicitly cite specific projects, role titles, and metrics from the context. "
    "Never mention you are an AI."
)

MULTI_QUERY_SPLIT_PROMPT = (
    """You are a search query rewriter for a recruitment assistant. 
    Generate exactly 3 distinct search queries based on the user's question to maximize retrieval recall from the candidate's profile.

    **The 3 Queries MUST approach the question from these 3 distinct angles:**

    1. **Conceptual Angle:** How would you ask this question at a high, abstract level? (e.g., "overall reputation", "general capabilities").
    2. **Role/Tech Angle:** What specific job titles, technical skills, or hard requirements are implied? (e.g., "Scrum Master", "Python expertise").
    3. **Evidence/Project Angle:** What concrete projects, metrics, or time-bound deliverables would prove the answer? (e.g., "projects delivered on time", "MVP in 2023").

    **Output Rules:**
    - Output **ONLY** a valid JSON array of 3 strings. No explanations, no markdown.
    - Queries must be 5 to 15 words long. No questions marks. Use declarative statements."""
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
    "based on provided information"
]
