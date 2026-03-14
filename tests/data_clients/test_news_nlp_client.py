import pytest
from user_data.strategies.data_clients.news_nlp_client import NewsNLPClient

try:
    import transformers  # noqa: F401
    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    _TRANSFORMERS_AVAILABLE = False

requires_transformers = pytest.mark.skipif(
    not _TRANSFORMERS_AVAILABLE,
    reason="transformers/FinBERT not installed — skipping NLP sentiment tests"
)

@pytest.fixture
def client():
    return NewsNLPClient()

def test_analyse_returns_score_between_0_and_1(client):
    score = client.analyse("Bitcoin surges to new all-time high on institutional demand")
    assert 0.0 <= score <= 1.0

@requires_transformers
def test_positive_headline_scores_above_0_5(client):
    score = client.analyse("Bitcoin surges to new all-time high on massive institutional demand")
    assert score > 0.5

@requires_transformers
def test_negative_headline_scores_below_0_5(client):
    score = client.analyse("Crypto market crashes, Bitcoin loses 40% in massive sell-off")
    assert score < 0.5

def test_empty_headline_returns_neutral(client):
    score = client.analyse("")
    assert score == 0.5
