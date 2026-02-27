from src.services.memory_store import embed_text


def test_embed_text_is_deterministic_and_normalized():
    text = "Long run moved to Sunday after discussing fatigue."
    first = embed_text(text, dim=64)
    second = embed_text(text, dim=64)

    assert len(first) == 64
    assert first == second

    norm = sum(v * v for v in first) ** 0.5
    assert 0.99 <= norm <= 1.01


def test_embed_text_handles_empty_content():
    vec = embed_text("", dim=32)
    assert len(vec) == 32
    assert all(v == 0 for v in vec)
