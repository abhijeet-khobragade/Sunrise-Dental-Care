import pytest

from app.knowledge import tokenize


def test_tokenize_drops_stopwords_and_plurals():
    assert tokenize("What are the prices for braces?") == ["price", "brace"]


@pytest.mark.parametrize(
    "question, expected_title",
    [
        ("How much does a root canal cost?", "Root canal treatment"),
        ("Are you open on Sunday?", "Opening hours"),
        ("Do you accept insurance cashless?", "Insurance"),
        ("What is the clinic address?", "Location and contact"),
        ("Price of clear aligners", "Braces and aligners"),
    ],
)
def test_search_finds_the_right_section(kb, question, expected_title):
    # The bot gives Claude the top 3 results, so the answer must be among them.
    titles = [chunk.title for chunk in kb.search(question, top_k=3)]
    assert expected_title in titles


@pytest.mark.xfail(reason="Keyword search can't tell 'located' means 'location'. Embeddings fix this.")
def test_search_understands_meaning(kb):
    titles = [chunk.title for chunk in kb.search("Where is the clinic located?", top_k=3)]
    assert "Location and contact" in titles


def test_search_with_no_match_returns_nothing(kb):
    assert kb.search("xylophone spaceship") == []
