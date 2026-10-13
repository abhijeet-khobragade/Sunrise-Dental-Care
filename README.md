# AI Customer Support Chatbot

A website chat assistant for a (fictional) dental clinic. It answers questions from the
clinic's own documents, checks real availability, books appointments into a database,
and hands difficult conversations to human staff.

**Built with:** Python · FastAPI · Claude API (tool use) · SQLAlchemy + SQLite · BM25 retrieval · vanilla JS · pytest

<!-- Add a screenshot or GIF here: it's the first thing recruiters look at -->

## Features

- **Answers from documents (RAG):** searches `knowledge/*.md` and answers only from what it finds, so it doesn't make up prices or policies
- **Appointment booking:** checks opening hours and free slots, validates phone numbers, and blocks double bookings at the database level
- **Human hand-off:** creates a ticket for staff when a customer asks for a person, complains, or needs medical advice
- **Chat widget UI:** quick-reply chips, typing indicator, action badges, full-screen on phones
- **Staff dashboard** at `/admin`: lists appointments and hand-off tickets (protected by a token)
- **Safe by design:** Claude can only act through validated tools, the UI escapes HTML, and refused or failed turns are rolled back
- **Tested:** 26 offline tests, with a fake Claude client so no API key is needed

## How it works

```
Browser (static/app.js)
   │  POST /api/chat {session_id, message}
   ▼
FastAPI (app/main.py)
   ▼
Chatbot loop (app/chatbot.py) ──► Claude API
   │      ▲                         │ "call search_knowledge_base(...)"
   │      └──── tool result ◄───────┘
   ▼
Tools (app/tools.py)
   ├─ search_knowledge_base ─► BM25 search over knowledge/*.md (app/knowledge.py)
   ├─ check_availability    ─► SQLite
   ├─ book_appointment      ─► SQLite
   └─ escalate_to_human     ─► SQLite
```

Claude never touches the database directly. It *asks* to call a tool; our Python code
validates the input, does the work, and sends the result back. The loop repeats until
Claude has a final answer.

## Run it locally

1. Create a virtual environment and install the dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows (on Mac/Linux: source .venv/bin/activate)
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env`, then add your `ANTHROPIC_API_KEY` (from https://console.anthropic.com) and choose an `ADMIN_TOKEN`.
3. Start the server:
   ```bash
   uvicorn app.main:app --reload
   ```
4. Open http://localhost:8000 for the chat and http://localhost:8000/admin for the staff dashboard. Interactive API docs are at http://localhost:8000/docs.

Run the tests with `pytest`.

**Cost tip:** the default model is Claude Opus 5.5 (best quality). Set
`CLAUDE_MODEL=claude-haiku-5-5` in `.env` while developing to make each message far cheaper.

## Use it for a different business

Replace the files in `knowledge/` with that business's information, change `BUSINESS_NAME`
in `.env`, and adjust `SERVICES` and `slots_for_day()` in `app/tools.py`.

## Roadmap (ideas for extending it yourself)

- [ ] **Semantic search:** replace BM25 with embeddings + a vector DB (Chroma or pgvector). There's an `xfail` test waiting for this in `tests/test_knowledge.py`
- [ ] **Streaming replies** so text appears word by word
- [ ] **Persist conversations** in the database (right now they're in memory and a restart clears them)
- [ ] **Cancel / reschedule** tools
- [ ] **Evaluation script:** 20 test questions with expected facts, scored automatically
- [ ] **WhatsApp channel** via the Twilio or Meta WhatsApp API
- [ ] **Docker + deployment** (Render / Railway), and **GitHub Actions** CI running pytest
- [ ] Switch SQLite to PostgreSQL for production
