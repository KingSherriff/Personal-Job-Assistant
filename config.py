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
BM25_MIN_SCORE=os.getenv("BM25_MIN_SCORE",1)

SYSTEM_PROMPT = (
    f"You are {CANDIDATE_NAME}'s portfolio assistant. "
    "Use ONLY the context below to answer. "
    "If the answer isn't in the context, say exactly: "
    f"'I don't have that detail — contact {CANDIDATE_EMAIL} or visit {GITHUB_LINK}.' "
    "Be concise. Instead of abstract summaries, explicitly cite specific projects, role titles, and metrics from the context. "
    "Never mention you are an AI."
)

MULTI_QUERY_SPLIT_PROMPT = (
    """Rewrite the user's question into 3 distinct search queries about the candidate.
    Rules:
    - Every query MUST mention 'the candidate'.
    - Cover different angles: one abstract, one role-specific, one project-specific.
    - Output ONLY a JSON array of 3 strings. No explanations."""
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

PRONOUNS = {
    r"how many years": f"how many years of experience does {CANDIDATE_NAME} have",
    r"does he": f"does {CANDIDATE_NAME}",
    r"is he": f"is {CANDIDATE_NAME}",
    r"was he": f"was {CANDIDATE_NAME}",
    r"has he": f"has {CANDIDATE_NAME}",
    r"have you": f"has {CANDIDATE_NAME}",
    r"did he": f"did {CANDIDATE_NAME}",
    r"can he": f"can {CANDIDATE_NAME}",
    r"would he": f"would {CANDIDATE_NAME}",
    r"are you": f"is {CANDIDATE_NAME}",
    r"his": f"{CANDIDATE_NAME}'s",
    r"your": f"{CANDIDATE_NAME}'s",
    r"the candidate": CANDIDATE_NAME,
    r"he|him|himself": CANDIDATE_NAME,
    r"you": CANDIDATE_NAME,
}
