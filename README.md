# CircuitWorks Support Agent

An AI customer-support agent for an electronics and robotics component shop. It is built with LangGraph as a multi-agent system. A single agent graph serves every channel: a Next.js storefront with a chat widget, real-time browser voice calls, a Streamlit chat app and a local voice app.

Customers can search the catalog, ask about specs, place and cancel orders, request returns and ask policy questions, by text or by voice. Staff manage fulfillment, returns, escalations and inventory from an admin panel.

> **Status:** this is a demo or reference implementation, not a production system. See [Known limitations](#known-limitations).

---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Running the application](#running-the-application)
- [Admin panel](#admin-panel)
- [API reference](#api-reference)
- [Design principles](#design-principles)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Known limitations](#known-limitations)

---

## Features

- **Multi-agent routing.** A supervisor classifies each message and sends it to one of four specialists: a product agent, an order agent, a policy agent or an escalation agent.
- **Omnichannel.** Web chat, browser voice, Streamlit and local voice all call the same compiled graph, so no business logic is duplicated between channels.
- **Real-time voice.** Deepgram handles streaming speech-to-text and ElevenLabs handles streaming text-to-speech. Barge-in is supported: talking over the assistant stops its playback.
- **Hybrid retrieval.** Chroma runs semantic search over products and policies using local ONNX MiniLM embeddings, so embeddings need no API key. Price and stock always come from SQL.
- **Safe order flow.** Orders go through a two-step prepare-then-confirm flow that the backend enforces. The LLM cannot create an order on its own.
- **Returns and refunds.** A complete return lifecycle with atomic state transitions, so an order can't be refunded twice.
- **Human handoff.** Escalations pause the conversation with LangGraph `interrupt()`, are saved to the database and can notify Slack.
- **Persistent conversations.** Graph state is checkpointed to SQLite, so conversations survive restarts.
- **Admin panel.** Dashboard, order fulfillment, return review, escalation triage and inventory management.
- **Real catalog data (optional).** Importers for the Mouser and Nexar (Octopart) distributor APIs.

## Architecture

```
          ┌──────────────────────── Channels ────────────────────────┐
          │  Next.js storefront    Browser voice     Streamlit   Local │
          │  (chat widget)         (WebSocket)       chat        voice │
          └───────────┬───────────────────┬──────────────┬───────┬───┘
                      │ POST /api/chat    │ /ws/voice    │       │
                      ▼                   ▼              │       │
               ┌──────────────── FastAPI (api/) ───────┐  │       │
               └───────────────────┬───────────────────┘  │       │
                                   ▼                      ▼       ▼
                    ┌────────── Shared LangGraph (graph.py) ──────────┐
                    │                                                  │
                    │   START ─► supervisor (intent classification)    │
                    │               ├─► product_agent                  │
                    │               ├─► order_agent                    │
                    │               ├─► policy_agent                   │
                    │               └─► escalation_agent ─► interrupt() │
                    └──────┬──────────────────┬────────────────┬──────┘
                           ▼                  ▼                ▼
                    Google Gemini      Chroma (RAG)      SQL database
                        (LLM)       products, policies  orders, stock,
                                                        customers, returns
```

Voice channels wrap the same graph. Deepgram turns speech into text, the graph produces a text reply, and ElevenLabs streams the reply back as audio.

## Tech stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph, LangChain |
| LLM | Google Gemini (`langchain-google-genai`) |
| Vector search | Chroma with local ONNX MiniLM-L6 embeddings |
| Database | SQLAlchemy 2 on SQLite (Postgres-ready) |
| Backend API | FastAPI, Uvicorn |
| Frontend | Next.js 16 (App Router), React 19, Tailwind CSS 4, TypeScript |
| Voice | Deepgram (STT), ElevenLabs (TTS), `sounddevice` |
| Other interfaces | Streamlit |
| Integrations | Slack (escalations), Tavily (spec web search), Mouser and Nexar (catalog import) |
| Testing | pytest |

## Getting started

### Prerequisites

- Python 3 (developed and tested on 3.14)
- Node.js 20 or later, with npm
- A [Google AI Studio](https://aistudio.google.com/) API key (required)
- Deepgram and ElevenLabs API keys (only needed for voice)

### Installation

```bash
git clone https://github.com/<your-username>/electronics-shop-agent.git
cd electronics-shop-agent

# Python environment
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux
pip install -r requirements.txt

# Environment variables
cp .env.example .env             # then set GOOGLE_API_KEY at minimum

# Frontend dependencies
cd web && npm install && cd ..
```

### Data setup

Nothing is seeded or reset automatically. Run these steps once, in order:

```bash
python -m data.generate_synthetic_data   # Uses the LLM to generate a demo catalog and policy docs
python -m scripts.ingest_products        # Embeds the catalog into Chroma (safe to re-run)
python -m scripts.ingest_policies        # Embeds the policy docs into Chroma (safe to re-run)
python -m scripts.seed_demo_data         # ⚠️ Resets demo customers and inventory
```

If the product ingest is interrupted, for example by rate limits, resume it with `python -m scripts.ingest_products --skip-existing`.

To use real distributor data instead of synthetic data, see [Using real catalog data](#using-real-catalog-data-optional).

## Configuration

All settings are read from `.env` through [`config.py`](config.py). See [`.env.example`](.env.example) for a template.

| Variable | Required for | Default / notes |
|---|---|---|
| `GOOGLE_API_KEY` | Everything | Gemini API key. The only variable checked at startup. |
| `GEMINI_MODEL` | Optional | `gemini-3.5-flash-lite` |
| `LLM_TEMPERATURE` | Optional | `0.2` |
| `DEEPGRAM_API_KEY`, `DEEPGRAM_MODEL` | Voice | Speech-to-text. The model defaults to `nova-3`. |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID` | Voice | Text-to-speech. Defaults to the "Rachel" voice and `eleven_flash_v2_5`. |
| `DATABASE_URL` | Optional | `sqlite:///./electronics_shop.db`. For Postgres, set this and install `psycopg2-binary`. |
| `CHROMA_PERSIST_DIR` | Optional | `./chroma_data` |
| `SLACK_WEBHOOK_URL` | Optional | Escalation notifications. Escalations are saved to the database even without it. |
| `TAVILY_API_KEY` | Optional | Web search fallback for product specs |
| `CONFIRMATION_TTL_MINUTES` | Optional | How long a pending order confirmation stays valid. Defaults to `10`. |
| `SESSION_SECRET_KEY` | Website | Signs session cookies. **Change it outside local development.** |
| `FRONTEND_ORIGIN` | Website | CORS and WebSocket origin allowlist. Defaults to `http://localhost:3000`. |
| `ADMIN_PASSWORD` | Admin panel | Leave it empty to disable the admin panel. There is no default. |
| `MOUSER_API_KEY` | Optional | Mouser **Search** API key, used only by the Mouser importer |
| `NEXAR_CLIENT_ID`, `NEXAR_CLIENT_SECRET` | Optional | Used only by the Nexar importer |

The frontend reads `NEXT_PUBLIC_API_URL` from `web/.env.local`. It defaults to `http://localhost:8000`.

Voice keys are checked only when a voice session starts, so text chat and the scripts work without them.

## Running the application

### Web storefront

Run the backend and the frontend in two separate terminals.

```bash
# Terminal 1: backend (from the project root, with the venv active)
uvicorn api.main:app --reload --port 8000

# Terminal 2: frontend
cd web
npm run dev
```

- Storefront: http://localhost:3000
- Interactive API docs: http://localhost:8000/docs

For a production build of the frontend, run `npm run build` and then `npm run start`.

**Demo accounts:** the seeded customers `cust-001` (Alice), `cust-002` (Ben) and `cust-003` (Priya) can be selected from the demo picker on `/login`. They have no password. You can also sign up for a password account.

| Route | Purpose |
|---|---|
| `/` | Home: featured products and categories |
| `/products`, `/products/[sku]` | Catalog search and product details |
| `/cart` | Shopping cart, stored in browser `localStorage` |
| `/checkout` | Two-step checkout: prepare, then confirm |
| `/login` | Log in, sign up or choose a demo customer |
| `/orders`, `/orders/[id]` | Order history, tracking and cancellation |
| `/admin/...` | Admin panel |

The chat widget appears on every page and can start a voice call. It shares the browser session, so an order placed by chat or voice appears under `/orders`.

### Streamlit chat and local voice

```bash
streamlit run interfaces/chat_app.py
python -m interfaces.voice_app       # Requires Deepgram and ElevenLabs keys and a microphone
```

## Admin panel

Set `ADMIN_PASSWORD` in `.env`, restart the backend, and open http://localhost:3000/admin.

| Page | Capabilities |
|---|---|
| `/admin` | Dashboard: orders to fulfill, returns to review, refunds due, open escalations, low stock |
| `/admin/orders` | View all orders, then move them through processing, shipped (with tracking) and delivered |
| `/admin/returns` | Approve or reject returns with a note, then process refunds |
| `/admin/escalations` | Triage human-handoff requests: set status, assign staff, record a resolution |
| `/admin/inventory` | Search SKUs, restock or write off stock, update prices |

Admin sessions use a separate cookie (`cw_admin`, valid for 12 hours) that is isolated from customer sessions. Changing `ADMIN_PASSWORD` signs out every admin session.

### Command-line operations

```bash
python -m scripts.ship_order processing <order_id>
python -m scripts.ship_order shipped <order_id> <tracking_number> [carrier]
python -m scripts.ship_order delivered <order_id>

python -m scripts.reset_demo_db      # Drops and recreates all tables (asks for confirmation)
```

### Using real catalog data (optional)

Both importers write to `data/catalog.json` in the same format. After importing, run `seed_demo_data` and `ingest_products` as usual.

```bash
python -m scripts.import_from_mouser [--max-requests 1000]   # Requires MOUSER_API_KEY
python -m scripts.import_from_nexar [--per-category 15]      # Requires NEXAR_CLIENT_ID/SECRET
```

Mouser allows 30 requests per minute and 1,000 per day. The importer paces itself and saves progress after every request.

## API reference

| Method and path | Description |
|---|---|
| `GET /api/health` | Health check |
| `POST /api/auth/signup`, `POST /api/auth/login` | Password accounts (bcrypt-hashed) |
| `GET /api/customers`, `POST /api/session` | Demo login: list the seeded customers and pick one |
| `GET /api/session`, `POST /api/logout` | Read or clear the current session |
| `GET /api/products?query=&category=&limit=` | List products or run a semantic search |
| `GET /api/products/{sku}`, `GET /api/categories` | Product details and the category list |
| `POST /api/checkout/prepare`, `POST /api/checkout/confirm` | Two-step checkout |
| `GET /api/orders`, `GET /api/orders/{id}`, `POST /api/orders/{id}/cancel` | The current customer's orders |
| `POST /api/chat` | Send one chat message to the agent graph |
| `WS /ws/voice` | Browser voice bridge: PCM16 16 kHz in, 24 kHz out, plus JSON events |
| `/api/admin/*` | Admin endpoints (require an admin session) |

Customer identity comes only from the signed, httponly `cw_session` cookie, never from the request body.

## Design principles

The system is built so that correctness and security hold no matter what the LLM does or is tricked into doing. Authorization lives in the backend, not in the prompt.

1. **The LLM can't place an order on its own.** The order agent has only `prepare_order` and `confirm_order`. `prepare_order` records a pending confirmation. `confirm_order` turns it into an order with one atomic conditional `UPDATE` that checks ownership, the conversation, the status and the expiry together. Starting a new prepare supersedes any earlier pending one.
2. **Identity is never a tool argument.** `customer_id` and `conversation_id` are bound into each turn's tools by a factory. The LLM can't set them, and a test asserts this.
3. **SQL is the single source of truth for price and stock.** Chroma is used only to find matching SKUs. Every search result is joined against the SQL inventory table, so a stale price can't reach a customer.
4. **State changes are atomic.** Cancellations, fulfillment steps, return approvals and refunds are each a single conditional `UPDATE` that checks the affected row count. Double cancellation, double shipping and double refunds can't happen. This is enforced by the database, not by prompt instructions.
5. **Privileged actions aren't agent tools.** Approving returns, processing refunds and shipping orders are plain backend functions that only the admin panel and CLI call. The customer-facing agent can't decide that a refund happened.
6. **Seeding is explicit.** No script silently seeds or resets data on startup.

## Testing

```bash
pytest tests/ -v
```

The suite has 57 tests. It covers order confirmation, order security and ownership, inventory concurrency (including simultaneous cancellations run in real threads), money handling, returns, retrieval-to-SQL joins and the admin API. The tests run against a real SQLite file per test. They don't make live LLM calls.

## Project structure

```
├── agents/          Supervisor, specialist agent nodes and graph state
├── api/             FastAPI backend: sessions, auth and routers
│   └── routers/     auth, customers, products, checkout, chat, voice, admin
├── data/            Catalog, policy documents and synthetic data generator
├── db/              SQLAlchemy models and engine/session setup
├── interfaces/      Streamlit chat, local voice app and shared voice engine
├── rag/             Chroma vector store and ingestion
├── scripts/         Ingestion, seeding, reset, catalog importers, fulfillment CLI
├── tests/           pytest suite
├── tools/           Agent tools and admin-only fulfillment and return functions
├── web/             Next.js storefront and admin panel
├── config.py        Central settings, loaded from .env
├── graph.py         Builds the shared LangGraph
├── llm.py           Gemini client factory
└── main.py          Prints the setup steps
```

## Known limitations

- **Demo authentication.** The demo customer picker logs in without a password, and `SESSION_SECRET_KEY` has an insecure default. Neither is suitable for deployment.
- **Shared admin password.** There are no per-admin accounts, no roles and no audit log. Resolving an escalation doesn't notify the customer or resume the paused conversation.
- **One agent per turn.** A message that mixes intents, such as a stock question and a return request together, is routed to a single agent.
- **Coarse return eligibility.** Returns don't take into account how long ago an order was delivered.
- **Naive UTC datetimes.** Datetimes are stored as naive UTC because SQLite drops timezone information. If you migrate to Postgres, switch to timezone-aware datetimes consistently.
- **No observability.** There is no tracing or structured logging.
- **Synthetic demo data.** The default catalog and policies are generated by the LLM.
- **Tests don't cover the LLM.** They check the backend guarantees directly, not the model's tool-selection behavior end to end.
