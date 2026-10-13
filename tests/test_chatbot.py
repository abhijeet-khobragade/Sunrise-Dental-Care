"""Tests the chatbot loop with a fake Claude client, so no API key or money is needed."""

from types import SimpleNamespace

from sqlalchemy import select

from app.chatbot import Chatbot
from app.database import Handoff


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(id, name, input):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def response(stop_reason, *content):
    return SimpleNamespace(stop_reason=stop_reason, content=list(content))


class FakeClient:
    """Returns pre-written responses in order and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        # Copy the message list: the bot keeps appending to the same list afterwards.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def make_bot(client, kb, session_factory):
    return Chatbot(client, kb, session_factory, business="Test Clinic", model="test-model", effort="low")


def test_plain_answer(kb, session_factory):
    client = FakeClient(response("end_turn", text("Hello! How can I help?")))
    reply = make_bot(client, kb, session_factory).reply("session-1", "hi")
    assert reply.text == "Hello! How can I help?"
    assert reply.actions == []


def test_tool_call_result_is_sent_back(kb, session_factory):
    client = FakeClient(
        response("tool_use", tool_use("t1", "search_knowledge_base", {"query": "root canal price"})),
        response("end_turn", text("A root canal costs ₹4,500 to ₹7,000.")),
    )
    reply = make_bot(client, kb, session_factory).reply("session-1", "root canal cost?")

    assert "₹4,500" in reply.text
    tool_result = client.requests[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "t1"
    assert "Root canal treatment" in tool_result["content"]


def test_bad_tool_input_is_reported_as_error(kb, session_factory):
    client = FakeClient(
        response("tool_use", tool_use("t1", "check_availability", {"date": "tomorrow"})),
        response("end_turn", text("Which date would you like?")),
    )
    make_bot(client, kb, session_factory).reply("session-1", "book me in")
    tool_result = client.requests[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True


def test_escalation_shows_action_badge(kb, session_factory):
    args = {"reason": "complaint", "summary": "Unhappy with wait time", "contact": "not provided"}
    client = FakeClient(
        response("tool_use", tool_use("t1", "escalate_to_human", args)),
        response("end_turn", text("I've passed this to our staff.")),
    )
    reply = make_bot(client, kb, session_factory).reply("session-1", "I want to complain")
    assert reply.actions == ["Sent to clinic staff"]
    with session_factory() as db:
        assert db.scalars(select(Handoff)).one().session_id == "session-1"


def test_refusal_does_not_break_the_conversation(kb, session_factory):
    client = FakeClient(
        response("refusal"),
        response("end_turn", text("We're open 9 to 6.")),
    )
    bot = make_bot(client, kb, session_factory)
    assert "can't help" in bot.reply("session-1", "something bad").text
    bot.reply("session-1", "what are your timings?")
    # The refused turn was removed, so the next request starts cleanly.
    assert client.requests[1]["messages"] == [{"role": "user", "content": "what are your timings?"}]


def test_conversations_are_kept_separate(kb, session_factory):
    client = FakeClient(response("end_turn", text("A")), response("end_turn", text("B")))
    bot = make_bot(client, kb, session_factory)
    bot.reply("session-1", "first")
    bot.reply("session-2", "second")
    assert len(client.requests[1]["messages"]) == 1
