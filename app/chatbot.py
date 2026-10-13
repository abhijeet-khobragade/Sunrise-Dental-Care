"""The chatbot: sends the conversation to Claude, runs the tools Claude asks for,
and loops until Claude has a final answer for the customer."""

import threading
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

import anthropic
from sqlalchemy.orm import sessionmaker

from app.knowledge import KnowledgeBase
from app.tools import TOOLS, ToolError, run_tool

MAX_TOOL_ROUNDS = 8  # safety limit on tool calls per customer message
MAX_SESSIONS = 500  # conversations kept in memory

SYSTEM_PROMPT = """You are the friendly virtual receptionist for {business}, chatting with \
customers on the clinic's website. Today is {today}.

How to help:
- Answer questions about the clinic only from search_knowledge_base results. If the \
documents don't cover something, say so and offer to connect the customer with staff. \
Never invent prices, timings or policies.
- To book: find out the service and preferred date, call check_availability, offer a \
few free slots, then collect the customer's name and 10-digit phone number. Repeat the \
details back and get a clear "yes" before calling book_appointment.
- Use escalate_to_human when the customer asks for a person, is unhappy, reports a \
billing problem, or needs medical advice. Ask for their name and phone number first \
if they're willing to share them.
- You are not a dentist. Don't diagnose. For severe pain, swelling, heavy bleeding \
or trauma, suggest an emergency visit or calling the clinic right away.

Style: warm, clear and brief (2-4 short sentences or a short list). Plain text with \
**bold** and "- " bullet points only. Reply in the customer's language (English, \
Hindi or Marathi)."""

ACTION_LABELS = {
    "book_appointment": "Appointment booked",
    "escalate_to_human": "Sent to clinic staff",
}


@dataclass
class ChatReply:
    text: str
    actions: list[str] = field(default_factory=list)  # shown as badges in the UI


class Chatbot:
    def __init__(
        self,
        client: anthropic.Anthropic,
        kb: KnowledgeBase,
        session_factory: sessionmaker,
        *,
        business: str,
        model: str,
        effort: str,
    ):
        self.client = client
        self.kb = kb
        self.session_factory = session_factory
        self.business = business
        self.model = model
        self.effort = effort
        # session_id -> list of messages. Kept in memory: a restart clears chats.
        self.histories: OrderedDict[str, list] = OrderedDict()
        self._locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)

    def reply(self, session_id: str, user_message: str) -> ChatReply:
        # One message at a time per conversation, so histories never interleave.
        with self._locks[session_id]:
            history = self._history(session_id)
            start = len(history)
            history.append({"role": "user", "content": user_message})
            try:
                return self._run(session_id, history)
            except Exception:
                del history[start:]  # undo this turn so the conversation stays valid
                raise

    def reset(self, session_id: str) -> None:
        self.histories.pop(session_id, None)

    def _history(self, session_id: str) -> list:
        if session_id not in self.histories:
            self.histories[session_id] = []
            if len(self.histories) > MAX_SESSIONS:
                self.histories.popitem(last=False)  # forget the oldest conversation
        self.histories.move_to_end(session_id)
        return self.histories[session_id]

    def _run(self, session_id: str, history: list) -> ChatReply:
        now = datetime.now()
        system = SYSTEM_PROMPT.format(business=self.business, today=f"{now:%A, %d %B %Y}")
        actions: list[str] = []
        start = len(history) - 1

        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                tools=TOOLS,
                messages=history,
                output_config={"effort": self.effort},
                # If Claude's safety filters decline a message, the API retries it on a
                # fallback model automatically instead of failing.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )

            if response.stop_reason == "refusal":
                del history[start:]
                return ChatReply(
                    "Sorry, I can't help with that here. You can call the clinic and our "
                    "staff will be happy to assist."
                )

            # Keep the full response (including thinking/tool blocks) in the history.
            history.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                text = "\n".join(b.text for b in response.content if b.type == "text").strip()
                return ChatReply(text or "Sorry, could you say that again?", actions)

            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = {"type": "tool_result", "tool_use_id": block.id}
                try:
                    with self.session_factory() as db:
                        result["content"] = run_tool(
                            block.name, block.input,
                            db=db, kb=self.kb, session_id=session_id, now=now,
                        )
                    if block.name in ACTION_LABELS:
                        actions.append(ACTION_LABELS[block.name])
                except ToolError as e:
                    result["content"] = f"Error: {e}"
                    result["is_error"] = True
                results.append(result)
            # All tool results go back together in a single user message.
            history.append({"role": "user", "content": results})

        del history[start:]  # gave up: drop the unfinished turn
        return ChatReply(
            "Sorry, I got stuck on that one. Could you rephrase, or ask to speak with our staff?",
            actions,
        )
