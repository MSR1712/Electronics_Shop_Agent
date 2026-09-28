"""
Central config. Loads from .env and exposes typed settings.
Every module imports from here instead of calling os.getenv() directly,
so swapping providers (e.g. Gemini -> OpenAI, SQLite -> Postgres) means
editing one place.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # LLM
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    # Voice I/O — used by interfaces/voice_app.py and api/routers/voice.py.
    # Deepgram (streaming STT) + ElevenLabs (streaming TTS) replaced the
    # earlier Gemini Live (native audio) engine — see interfaces/voice_engine.py
    # for why (Gemini Live did turn-taking/VAD/barge-in for free; this pair
    # doesn't, so voice_engine.py builds it on top of Deepgram's streaming
    # endpointing + speech-started events).
    deepgram_api_key: str = os.getenv("DEEPGRAM_API_KEY", "")
    deepgram_model: str = os.getenv("DEEPGRAM_MODEL", "nova-3")

    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    # "Rachel" — one of ElevenLabs' premade voices, available on every account.
    elevenlabs_voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    # eleven_flash_v2_5: lowest latency, tuned for real-time conversation.
    elevenlabs_model_id: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5")

    # Database — SQLite by default, swappable to Postgres via env var
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./electronics_shop.db")

    # Chroma
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
    chroma_collection_products: str = "product_catalog"
    chroma_collection_policies: str = "company_policies"

    # Escalation
    slack_webhook_url: str = os.getenv("SLACK_WEBHOOK_URL", "")

    # Order confirmation workflow (see tools/order_tools.py)
    confirmation_ttl_minutes: int = int(os.getenv("CONFIRMATION_TTL_MINUTES", "10"))

    # api/ session cookie signing (demo auth only — see api/session.py).
    session_secret_key: str = os.getenv("SESSION_SECRET_KEY", "dev-only-insecure-secret-change-me")

    # Shared password for the /admin panel (api/admin_session.py). Empty
    # means the admin panel is disabled — there is deliberately no default.
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")

    # The Next.js dev origin — used for both the api/ CORS allowlist and the
    # api/routers/voice.py WebSocket's manual Origin check (CORSMiddleware
    # does not cover WebSocket upgrades).
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

    # Web search fallback
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # Mouser Electronics Search API — used only by scripts/import_from_mouser.py
    # as a real-data alternative to data/generate_synthetic_data.py.
    mouser_api_key: str = os.getenv("MOUSER_API_KEY", "")

    # Nexar (Octopart) Supply API — used only by scripts/import_from_nexar.py,
    # another real-data alternative. OAuth2 client-credentials app from
    # https://portal.nexar.com/ under the "supply.domain" scope.
    nexar_client_id: str = os.getenv("NEXAR_CLIENT_ID", "")
    nexar_client_secret: str = os.getenv("NEXAR_CLIENT_SECRET", "")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def validate(self) -> None:
        missing = []
        if not self.google_api_key:
            missing.append("GOOGLE_API_KEY")
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

    def validate_voice(self) -> None:
        """Separate from validate(): only the voice interfaces (local
        interfaces/voice_app.py, api/routers/voice.py's WebSocket) need
        Deepgram/ElevenLabs — text-only chat and the admin/data scripts
        must keep working without them configured."""
        missing = []
        if not self.deepgram_api_key:
            missing.append("DEEPGRAM_API_KEY")
        if not self.elevenlabs_api_key:
            missing.append("ELEVENLABS_API_KEY")
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables for voice: {', '.join(missing)}"
            )


settings = Settings()
