"""Tests for chat SSE endpoint and conversation CRUD."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


# ---------------------------------------------------------------------------
# Helpers for mocking the Anthropic async streaming API
# ---------------------------------------------------------------------------


def _make_text_delta_event(text: str):
    """Create a mock content_block_delta event with text."""
    event = MagicMock()
    event.type = "content_block_delta"
    event.delta = MagicMock()
    event.delta.type = "text_delta"
    event.delta.text = text
    return event


def _make_content_block_start_event(block_type: str = "text", name: str = ""):
    """Create a mock content_block_start event."""
    event = MagicMock()
    event.type = "content_block_start"
    event.content_block = MagicMock()
    event.content_block.type = block_type
    if block_type == "text":
        event.content_block.text = ""
    elif block_type == "tool_use":
        event.content_block.name = name
    return event


def _make_final_message(stop_reason: str = "end_turn", content_text: str = "Hello!"):
    """Create a mock final message."""
    msg = MagicMock()
    msg.stop_reason = stop_reason
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = content_text
    msg.content = [text_block]
    return msg


class MockAsyncStream:
    """Mock for the async stream context manager returned by client.messages.stream()."""

    def __init__(self, events, final_message):
        self._events = events
        self._final_message = final_message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def __aiter__(self):
        return self._async_iter()

    async def _async_iter(self):
        for event in self._events:
            yield event

    async def get_final_message(self):
        return self._final_message


def _done_conversation_id(body: str) -> str:
    for line in body.strip().split("\n"):
        if not line.startswith("data:"):
            continue
        payload = json.loads(line[len("data:"):].strip())
        if "conversation_id" in payload:
            return payload["conversation_id"]
    raise AssertionError("done event with conversation_id not found")


# ---------------------------------------------------------------------------
# POST /api/v1/chat — SSE streaming
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_returns_sse_stream():
    """POST /api/v1/chat should return 200 with SSE content type."""
    events = [
        _make_content_block_start_event("text"),
        _make_text_delta_event("Hello "),
        _make_text_delta_event("there!"),
    ]
    final_msg = _make_final_message(stop_reason="end_turn", content_text="Hello there!")

    mock_stream = MockAsyncStream(events, final_msg)

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream)

    with patch("src.agent.coach.client", mock_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/chat",
                json={"message": "How should I train today?"},
            )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    # Parse SSE events from response body
    body = resp.text
    sse_events = []
    for line in body.strip().split("\n"):
        if line.startswith("data:"):
            data_str = line[len("data:"):].strip()
            try:
                sse_events.append(json.loads(data_str))
            except json.JSONDecodeError:
                pass

    # Should have token events and a done event
    event_types = set()
    for line in body.strip().split("\n"):
        if line.startswith("event:"):
            event_types.add(line[len("event:"):].strip())

    assert "token" in event_types or "done" in event_types


@pytest.mark.asyncio
async def test_chat_with_conversation_id():
    """POST /api/v1/chat with conversation_id should work."""
    events = [
        _make_text_delta_event("Sure!"),
    ]
    final_msg = _make_final_message(stop_reason="end_turn", content_text="Sure!")
    mock_stream = MockAsyncStream(events, final_msg)

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream)

    fake_id = str(uuid4())

    with patch("src.agent.coach.client", mock_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/chat",
                json={
                    "message": "What about tomorrow?",
                    "conversation_id": fake_id,
                },
            )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_chat_without_conversation_id_starts_new_conversation():
    """A missing conversation_id should mean a fresh server-side conversation."""
    events = [_make_text_delta_event("ok")]
    final_msg = _make_final_message(stop_reason="end_turn", content_text="ok")

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.stream = MagicMock(
        side_effect=[
            MockAsyncStream(events, final_msg),
            MockAsyncStream(events, final_msg),
        ]
    )

    with patch("src.agent.coach.client", mock_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.post(
                "/api/v1/chat",
                json={"message": "start isolated chat one"},
            )
            second = await client.post(
                "/api/v1/chat",
                json={"message": "start isolated chat two"},
            )

    assert first.status_code == 200
    assert second.status_code == 200
    assert _done_conversation_id(first.text) != _done_conversation_id(second.text)


# ---------------------------------------------------------------------------
# GET /api/v1/conversations — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_conversations():
    """GET /api/v1/conversations should return a list."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/conversations")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# GET /api/v1/conversations/{id} — get single
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_conversation_not_found():
    """GET /api/v1/conversations/{id} should return 404 for nonexistent."""
    fake_id = str(uuid4())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/api/v1/conversations/{fake_id}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_conversation_paginates_history():
    """GET /api/v1/conversations/{id} should support cursor pagination metadata."""
    events = [_make_text_delta_event("ok")]
    final_msg = _make_final_message(stop_reason="end_turn", content_text="ok")
    mock_stream = MockAsyncStream(events, final_msg)
    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream)

    with patch("src.agent.coach.client", mock_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first_chat = await client.post(
                "/api/v1/chat",
                json={"message": "history message 1"},
            )
            assert first_chat.status_code == 200
            conv_id = _done_conversation_id(first_chat.text)

            await client.post(
                "/api/v1/chat",
                json={
                    "message": "history message 2",
                    "conversation_id": conv_id,
                },
            )
            await client.post(
                "/api/v1/chat",
                json={
                    "message": "history message 3",
                    "conversation_id": conv_id,
                },
            )
            conversations_resp = await client.get("/api/v1/conversations")
            assert conversations_resp.status_code == 200
            conv_id = conversations_resp.json()[0]["id"]
            first_page = await client.get(
                f"/api/v1/conversations/{conv_id}",
                params={"limit": 2},
            )

    assert first_page.status_code == 200
    first_data = first_page.json()
    assert len(first_data["messages"]) == 2
    assert first_data["history"]["has_more"] is True
    assert first_data["history"]["next_before"] is not None

    with patch("src.agent.coach.client", mock_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            second_page = await client.get(
                f"/api/v1/conversations/{conv_id}",
                params={
                    "limit": 2,
                    "before": first_data["history"]["next_before"],
                },
            )

    assert second_page.status_code == 200
    second_data = second_page.json()
    assert len(second_data["messages"]) >= 1
    first_ids = {msg["id"] for msg in first_data["messages"]}
    second_ids = {msg["id"] for msg in second_data["messages"]}
    assert first_ids.isdisjoint(second_ids)


# ---------------------------------------------------------------------------
# DELETE /api/v1/conversations/{id} — delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_conversation_not_found():
    """DELETE /api/v1/conversations/{id} should return 404 for nonexistent."""
    fake_id = str(uuid4())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(f"/api/v1/conversations/{fake_id}")

    assert resp.status_code == 404
