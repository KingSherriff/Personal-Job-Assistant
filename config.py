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
BM25_MIN_SCORE=os.getenv("BM25_MIN_SCORE", 1)

REFUSAL = (
    f"Those details are not available in {CANDIDATE_NAME}'s portfolio. "
    f"Reach out at {CANDIDATE_EMAIL} or visit {GITHUB_LINK}."
)

FALLBACK = REFUSAL

SYSTEM_PROMPT = (
    f"You are {CANDIDATE_NAME}'s portfolio assistant. "
    "Answer using ONLY the context below. "
    "Do not infer, estimate, or calculate facts the context does not state — "
    "if it gives dates but no total, do not compute a duration; if it says "
    "'led a team' with no number, do not give a team size. "
    "If part of the question is supported and part isn't, answer the supported part and briefly name what's missing in your own words."
    f"Use the exact sentence '{REFUSAL}' ONLY when the context supports nothing at all, and in that case output it alone with no other text. "
    "Two to four sentences. Name specific projects, role titles, employers, and "
    "metrics from the context rather than summarizing abstractly. "
    f"Write about {CANDIDATE_NAME} in the third person. "
    "Answer directly — no preamble, no 'based on the context', no sign-off."
)

MULTI_QUERY_SPLIT_PROMPT = (
    """Rewrite the user's question into 3 search queries about the candidate.
    Rules:
    - Every query MUST name the candidate explicitly.
    - Write natural questions, not keyword lists.
    - Cover genuinely different angles: one about skills or capabilities, one about
      roles, employers, or responsibilities, one about specific named projects,
      technologies, or results.
    - The three queries must not be paraphrases of each other. If they would
      retrieve the same documents, rewrite them.
    - Output ONLY a JSON array of 3 strings. No explanations."""
)

QUESTION = (
    """Question: {question}
    Context from {candidate_name}'s portfolio:
    ---
    {context}
    ---
    Answer the question using only the context above."""
)

PERSONA_BREAKS = [
    "as an ai",
    "as a language model",
    "i am an ai",
    "i'm an ai",
    "i was created by",
    "i don't have personal",
    "i don't possess",
    "my training",
]

SOFT_SIGNALS = [
    "i cannot",
    "i'm not able to",
    "i don't have access",
    "based on provided information",
    "developed by",
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
