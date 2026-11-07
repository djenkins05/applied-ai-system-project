"""Documentation stays in sync with the code: diagram source, embedded copy, and cited evidence files."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
DIAGRAM = (ROOT / "diagrams" / "architecture.mmd").read_text(encoding="utf-8")


def test_diagram_source_is_a_flowchart_and_embedded_verbatim_in_the_readme():
    assert "flowchart TD" in DIAGRAM
    assert "```mermaid\n" + DIAGRAM.rstrip("\n") + "\n```" in README


def test_diagram_names_real_modules_and_functions():
    for name in ("guardrails.screen_input", "llm.interpret_preferences", "preferences.parse_preferences",
                 "recommender.recommend_songs", "fallback.manual_to_preferences",
                 "explain.validate_explanations", "feedback.py", "reliability_log"):
        assert name in DIAGRAM
        module = name.split(".")[0].replace(".py", "")
        assert (ROOT / "src" / f"{module}.py").exists()


def test_every_evidence_path_cited_in_the_docs_exists():
    for doc in ("README.md", "docs/rubric_coverage.md", "model_card.md", "ai_interactions.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        for path in set(re.findall(r"`((?:docs|evals|diagrams|src|tests)/[\w./-]+\.\w+)`", text)):
            assert (ROOT / path).exists(), f"{doc} cites missing file {path}"


def test_readme_labels_example_runs_distinctly():
    for label in ("REAL GEMINI RUN", "OFFLINE MOCK RUN", "MANUAL-ONLY RUN"):
        assert label in README
