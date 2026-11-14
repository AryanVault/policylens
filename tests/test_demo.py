import pytest

from policylens import demo, llm


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY_PAYG", raising=False)


def test_demo_is_default_and_needs_no_key(capsys):
    assert demo.main([]) == 0
    out = capsys.readouterr().out
    assert "demo mode - no API calls" in out
    assert "claude-haiku-5-5:low" in out


def test_demo_shows_one_document_against_answer_key(capsys):
    assert demo.main(["--doc", "doc_034"]) == 0
    out = capsys.readouterr().out
    assert "[answer key]" in out
    assert "MISS sum_insured" in out  # Sonnet's saved 10x misread is shown as a miss


def test_unknown_document_is_reported(capsys):
    assert demo.main(["--doc", "doc_999"]) == 1


def test_live_refuses_without_key(capsys):
    assert demo.main(["--live", "--doc", "doc_001"]) == 2
    assert "needs ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_live_requires_a_target():
    with pytest.raises(SystemExit):
        demo.main(["--live"])


def test_pdf_without_live_is_rejected():
    with pytest.raises(SystemExit):
        demo.main(["--pdf", "x.pdf"])


def test_make_client_refuses_without_key():
    with pytest.raises(SystemExit, match=r"ANTHROPIC_API_KEY \(or ANTHROPIC_API_KEY_PAYG\) is not set"):
        llm.make_client()
