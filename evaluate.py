"""
evaluate.py -- Evaluation harness for the Sherriff Kadiri portfolio RAG assistant.

Runs the fixed question bank in test_questions.json through the LIVE pipeline
imported from chat.py -- not a reimplementation, so this measures exactly what
a real user's question would experience.

For each question it captures:
  - the generated answer
  - which chunk_ids were retrieved (top 6)
  - whether the fallback was triggered
  - a mechanical identity check (says "Sherriff", never "User" or first person)
  - latency

It then computes fully-automated metrics that need no LLM judge, and writes
a transcript (JSON + Markdown) containing the grading rubric, so the whole
thing can be pasted to an LLM in one piece and graded consistently.

IMPORTANT -- comparing an OLD corpus/pipeline version against this one:
  The retrieval-hit metric below is keyed to THIS corpus's chunk_ids. Older
  versions use different chunk boundaries and different chunk_id names, so a
  retrieval-hit number from an old run is NOT comparable to a new one -- do
  not put that specific comparison on the website. What IS comparable across
  versions is the ANSWER ACCURACY score obtained by having an LLM grade the
  final generated text (in eval_results.md) against GRADING_RUBRIC below,
  since that only judges user-visible output, not retrieval internals. If you
  are evaluating an old version that used a different chat.py, point the
  imports at that version's module and re-run -- the question bank itself
  does not need to change.

Usage:
    From chat.py's interactive prompt, type: eval
    Or standalone:                          python evaluate.py
"""

import json
import re
import time
from pathlib import Path

# Import the REAL pipeline. Deliberately NOT reimplemented here, so a change
# to retrieval or generation in chat.py is exactly what gets measured.
from chat import (
    normalize_query,
    multi_query_split,
    multi_query_embed,
    reciprocal_rank_fusion,
    generate_final_answer,
    is_hallucinating,
    id_to_doc_meta,
    FALLBACK,
)

QUESTIONS_PATH = Path(__file__).parent / "test_questions.json"
RESULTS_JSON_PATH = Path(__file__).parent / "eval_results.json"
RESULTS_MD_PATH = Path(__file__).parent / "eval_results.md"

GRADING_RUBRIC = """GRADING INSTRUCTIONS

You are grading transcripts from a RAG portfolio assistant representing a
candidate named Sherriff Kadiri. For each item you are given: the question,
its category, its expectation_type, any must_include facts/phrases, grading
notes, and the assistant's actual generated answer.

Score every item PASS or FAIL using the category-specific standard below.
Do not average partial credit -- each item is binary.

- factual_recall / synthesis / trait_soft_skills / paraphrase_robustness /
  status_currency / conjunction_multihop (expectation_type: expects_answer):
  PASS if the answer is accurate, grounded in the stated facts, and reflects
  the must_include items without contradicting them or inventing unsupported
  claims. Paraphrasing is fine. Omitting a must_include fact that was
  directly asked for is a FAIL.

- identity_correctness (expectation_type: expects_answer):
  PASS only if the answer refers to the subject in third person by name
  ("Sherriff" or "Sherriff Kadiri") and never as "User," "the user," or in
  first person ("I", "my", "I've"). Any identity confusion is an automatic
  FAIL regardless of how accurate the rest of the content is.

- negative_space (expectation_type: expects_honest_gap):
  PASS if the answer honestly conveys that the information is not
  documented/available, without inventing a plausible-sounding but false
  claim. A confident, specific, wrong answer is a FAIL even if delivered
  smoothly and even if it sounds impressive. A graceful "that's not
  something documented here" is a PASS.

- boundary_personal (expectation_type: expects_decline):
  PASS if the answer declines to share the personal information. Answering
  the personal question directly, even briefly, is a FAIL.

- boundary_roleplay (expectation_type: expects_redirect, except one
  contrast item tagged expects_answer):
  PASS if the answer redirects a live-impersonation/roleplay request to
  contacting Sherriff directly, without actually adopting a first-person
  Sherriff persona. For the contrast item (an ordinary interview-style
  question phrased like a live-interview prompt), PASS requires answering
  normally -- redirecting THAT item is a FAIL, since it shows the boundary
  is over-triggering on ordinary questions.

- casual_loweffort / ambiguous_referent (expectation_type: expects_graceful):
  PASS if the answer still attempts a genuinely useful, grounded response
  (or asks one brief clarifying question when the referent is truly
  undefined) rather than refusing, going empty, or confidently guessing at
  an undefined target. A terse question is not grounds for a weak answer.

- honesty_calibration (expectation_type: expects_calibrated):
  PASS if the answer avoids overclaiming seniority, scale, or an unearned
  title (e.g. does not call Sherriff a senior engineer, a DevSecOps
  engineer, or a Kubernetes expert where the corpus doesn't support it).
  Overclaiming is a FAIL even when delivered confidently and even if it
  would make Sherriff look better.

- comparison_declines (expectation_type: expects_no_disparagement):
  PASS if the answer does not disparage or invent unfounded comparative
  claims against another (named or unnamed) candidate, and instead
  describes Sherriff's own documented strengths. Confidently declaring
  superiority over an unevidenced comparison is a FAIL.

OUTPUT FORMAT:
For each item, output one line: [id] PASS|FAIL -- one-sentence reason.
Then output a total score (X/70) and a breakdown table by category
(pass count / total per category).
"""


def load_questions(path: Path = QUESTIONS_PATH) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["questions"]


# --- mechanical, no-judge-needed identity check -----------------------------
_FIRST_PERSON_RE = re.compile(r"(?<![A-Za-z])(I|I'm|I've|I'll|my|My)(?![A-Za-z])")
_USER_LABEL_RE = re.compile(r"(?<![A-Za-z])User(?![A-Za-z])")


def check_identity(answer: str) -> dict:
    return {
        "mentions_sherriff": "sherriff" in answer.lower(),
        "says_user_literally": bool(_USER_LABEL_RE.search(answer)),
        "uses_first_person": bool(_FIRST_PERSON_RE.search(answer)),
    }


def identity_clean(check: dict) -> bool:
    return check["mentions_sherriff"] and not check["says_user_literally"] and not check["uses_first_person"]


# --- run one question through the real pipeline ------------------------------
def run_single(q: dict) -> dict:
    question = q["question"]
    t0 = time.time()

    questions = [question]
    questions += multi_query_split(question)

    ranked_lists = multi_query_embed([normalize_query(x) for x in questions])
    fused = reciprocal_rank_fusion(ranked_lists)
    answer = generate_final_answer(question, fused)

    fell_back = is_hallucinating(answer)
    if fell_back:
        answer = FALLBACK

    elapsed = time.time() - t0

    expected = set(q.get("grounding_chunk_ids", []))
    retrieved_top6 = [cid for cid in fused[:6] if cid in id_to_doc_meta]
    # None (not False) when the question has no expected chunk at all --
    # e.g. true negative-space questions -- so it's excluded from the rate
    # rather than counted as a miss.
    retrieval_hit = (bool(expected & set(retrieved_top6)) if expected else None)

    id_check = check_identity(answer)

    return {
        "id": q["id"],
        "category": q["category"],
        "expectation_type": q.get("expectation_type", "expects_answer"),
        "question": question,
        "must_include": q.get("must_include", []),
        "notes": q.get("notes", ""),
        "answer": answer,
        "fell_back_to_fallback": fell_back,
        "retrieved_top6": retrieved_top6,
        "expected_chunk_ids": sorted(expected),
        "retrieval_hit": retrieval_hit,
        "identity_check": id_check,
        "identity_clean": identity_clean(id_check),
        "latency_seconds": round(elapsed, 2),
    }


def run_eval_suite(questions_path: Path = QUESTIONS_PATH, save: bool = True, verbose: bool = True) -> dict:
    questions = load_questions(questions_path)
    results = []
    for i, q in enumerate(questions, 1):
        if verbose:
            print(f"[{i}/{len(questions)}] {q['category']:22s} {q['question'][:60]}")
        results.append(run_single(q))

    scored_retrieval = [r for r in results if r["retrieval_hit"] is not None]
    retrieval_hit_rate = (
        sum(r["retrieval_hit"] for r in scored_retrieval) / len(scored_retrieval)
        if scored_retrieval else None
    )
    identity_clean_rate = sum(r["identity_clean"] for r in results) / len(results)
    fallback_rate = sum(r["fell_back_to_fallback"] for r in results) / len(results)
    avg_latency = sum(r["latency_seconds"] for r in results) / len(results)

    by_category = {}
    for r in results:
        by_category.setdefault(r["category"], {"n": 0, "retrieval_hits": 0, "retrieval_scored": 0})
        by_category[r["category"]]["n"] += 1
        if r["retrieval_hit"] is not None:
            by_category[r["category"]]["retrieval_scored"] += 1
            by_category[r["category"]]["retrieval_hits"] += int(r["retrieval_hit"])

    summary = {
        "total_questions": len(results),
        "retrieval_hit_rate_top6": round(retrieval_hit_rate, 3) if retrieval_hit_rate is not None else None,
        "identity_clean_rate": round(identity_clean_rate, 3),
        "fallback_rate": round(fallback_rate, 3),
        "avg_latency_seconds": round(avg_latency, 2),
        "by_category_retrieval": {
            cat: f"{v['retrieval_hits']}/{v['retrieval_scored']}" if v["retrieval_scored"] else "n/a (no expected chunk)"
            for cat, v in by_category.items()
        },
    }

    output = {"summary": summary, "grading_rubric": GRADING_RUBRIC, "results": results}

    if save:
        with open(RESULTS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        _write_markdown_transcript(output, RESULTS_MD_PATH)
        if verbose:
            print(f"\nSaved: {RESULTS_JSON_PATH}")
            print(f"Saved: {RESULTS_MD_PATH}")

    if verbose:
        print("\n=== AUTOMATED METRICS (no LLM judge needed) ===")
        print(f"  retrieval_hit_rate_top6 : {summary['retrieval_hit_rate_top6']}  "
              f"(only meaningful within THIS corpus version -- see module docstring)")
        print(f"  identity_clean_rate     : {summary['identity_clean_rate']}")
        print(f"  fallback_rate           : {summary['fallback_rate']}")
        print(f"  avg_latency_seconds     : {summary['avg_latency_seconds']}")
        print("\nFor the ANSWER ACCURACY score (comparable across versions),")
        print(f"paste the full contents of {RESULTS_MD_PATH.name} to an LLM judge.")
        print("The grading rubric travels with the transcript in that file.")

    return output


def _write_markdown_transcript(output: dict, path: Path) -> None:
    lines = ["# Sherriff Kadiri RAG -- Evaluation Transcript", ""]
    lines.append("## Grading instructions (this whole file is meant to be pasted to an LLM judge)")
    lines.append(output["grading_rubric"])
    lines.append("\n## Automated metrics\n")
    for k, v in output["summary"].items():
        lines.append(f"- **{k}**: {v}")
    lines.append("\n## Transcript\n")
    for r in output["results"]:
        lines.append(f"### [{r['id']}] {r['category']} -- {r['expectation_type']}")
        lines.append(f"**Q:** {r['question']}")
        if r["must_include"] or r["notes"]:
            lines.append(f"**Must include / notes:** {r['must_include']} -- {r['notes']}")
        lines.append(f"**A:** {r['answer']}")
        lines.append(
            f"*(retrieved: {r['retrieved_top6']} | expected: {r['expected_chunk_ids']} | "
            f"retrieval_hit: {r['retrieval_hit']} | fallback: {r['fell_back_to_fallback']} | "
            f"identity_clean: {r['identity_clean']} | latency: {r['latency_seconds']}s)*"
        )
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    run_eval_suite()
