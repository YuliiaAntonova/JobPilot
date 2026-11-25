import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root = parent of job_application/ (define before load_dotenv)
REPO_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(REPO_ROOT / ".env")
load_dotenv()  # optional override from cwd


def _resolve_jwt_secret(raw: str) -> str:
    """
    HS256 рекомендует ключ ≥32 байт (RFC 7518). Короткий dev-секрет стабильно
    растягиваем через SHA256 — предупреждение PyJWT исчезает; после смены нужен re-login.
    """
    text = (raw or "").strip()
    if len(text.encode("utf-8")) >= 32:
        return text
    return hashlib.sha256(f"job_app_jwt_v1:{text}".encode("utf-8")).hexdigest()

# PostgreSQL (SQLAlchemy URL). Example:
# postgresql+psycopg2://USER:PASSWORD@127.0.0.1:5432/job_application
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

DATA_ROOT = Path(os.getenv("JOB_APP_DATA_ROOT", str(REPO_ROOT / "data")))
# Prefer data/storage/jobs; fall back to legacy data/jobs if that dir already exists.
_JOBS_DEFAULT = DATA_ROOT / "storage" / "jobs"
_JOBS_LEGACY = DATA_ROOT / "jobs"
JOBS_DIR = Path(
    os.getenv(
        "JOB_APP_JOBS_DIR",
        str(_JOBS_LEGACY if _JOBS_LEGACY.is_dir() and not _JOBS_DEFAULT.is_dir() else _JOBS_DEFAULT),
    )
).expanduser()

# LLM по умолчанию (override with APP_LLM_MODEL env).
# openai:gpt-4o-mini — основной мозг (профиль, RAG fill, cover letter, ATS).
# cursor:… — Cursor SDK; groq:… / google:… — aisuite.
# CrewAI tailor отдельно: OPENAI_MODEL_NAME (тоже gpt-4o-mini по умолчанию).
# При 429/TPM см. повторные попытки в llm.chat_completion_text: JOB_APP_LLM_RATELIMIT_RETRIES (default 8).
# Подробные print-этапы пайплайна: JOB_APP_PIPELINE_VERBOSE=1 (логируется только при True).
APP_LLM_MODEL = os.getenv("APP_LLM_MODEL", "openai:gpt-4o-mini")
CURSOR_API_KEY = os.getenv("CURSOR_API_KEY", "").strip()
CURSOR_MODEL = os.getenv("CURSOR_MODEL", "composer-2.5").strip() or "composer-2.5"
# LlamaCloud Parse for resume PDF → RAG prepare.
LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY", "").strip()
LLAMA_CLOUD_BASE_URL = os.getenv("LLAMA_CLOUD_BASE_URL", "").strip()
EMBED_BACKEND = (os.getenv("EMBED_BACKEND") or "huggingface").strip().lower()
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "BAAI/bge-small-en-v1.5").strip()
_RAG_DEFAULT = DATA_ROOT / "storage" / "rag"
_RAG_LEGACY = DATA_ROOT / "rag_storage"
RAG_PREPARE_STORAGE = Path(
    os.getenv(
        "RAG_PREPARE_STORAGE",
        str(_RAG_LEGACY if _RAG_LEGACY.is_dir() and not _RAG_DEFAULT.is_dir() else _RAG_DEFAULT),
    )
).expanduser()

# Resume tailor: crew_l7 (default, L7 CrewAI + OpenAI) or notebook (legacy Untitled pipeline).
TAILORING_PIPELINE = os.getenv("TAILORING_PIPELINE", "crew_l7").strip() or "crew_l7"
# Legacy notebook tailor / cover-letter notebook path. Set 0 to refuse TAILORING_PIPELINE=notebook.
ALLOW_LEGACY_TAILORING = os.getenv("ALLOW_LEGACY_TAILORING", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# CrewAI / markdown_to_cv_json (exact L7 behavior).
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini").strip() or "gpt-4o-mini"
# Live CrewAI agent logs in uvicorn/CLI (Working Agent / Starting Task / Final Answer).
# Same as L7 notebook Agent(..., verbose=True) + Crew(..., verbose=True). Default on.
JOB_APP_CREW_VERBOSE = os.getenv("JOB_APP_CREW_VERBOSE", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# Also implements the older JOB_APP_PIPELINE_VERBOSE alias.
if os.getenv("JOB_APP_PIPELINE_VERBOSE", "").strip().lower() in ("1", "true", "yes", "on"):
    JOB_APP_CREW_VERBOSE = True

# Размер батча для fill_form_from_resume_json (оставлен для тестов/скриптов).
# Lesson 5: параллельное заполнение полей — env JOB_APP_HITL_FIELD_CONCURRENCY (см. l5_hitl_workflow.py).
# Прим.: RUN_HITL_DEMO из Jupyter (llm.ipynb) не является переменной окружения и не задаётся здесь —
# через API HITL идёт по статусу needs_review после фонового run_job().
FIELDS_PER_BATCH = int(os.getenv("JOB_APP_FIELDS_PER_BATCH", "8"))

# POST /jobs: минимум символов в resume_text если PDF не приложен (текст из кабинета).
RESUME_TEXT_MIN_CHARS = max(40, int(os.getenv("JOB_APP_RESUME_TEXT_MIN_CHARS", "80")))

# JobBERT skill match — POST /analyze/job-description
JOBBERT_KNOWLEDGE_MODEL = os.getenv("JOBBERT_KNOWLEDGE_MODEL", "jjzha/jobbert_knowledge_extraction")
JOBBERT_MIN_ENTITY_SCORE = float(os.getenv("JOBBERT_MIN_ENTITY_SCORE", "0.60"))
JOBBERT_SEMANTIC_THRESHOLD = float(os.getenv("JOBBERT_SEMANTIC_THRESHOLD", "0.80"))
MATCH_SCORE_MODEL = os.getenv("MATCH_SCORE_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
MATCH_SCORE_WARMUP = os.getenv("MATCH_SCORE_WARMUP", "1").strip().lower() in ("1", "true", "yes")

# Phrase-level ATS (L4 semantic_search) — discovery vs diff thresholds
PHRASE_DISCOVERY_THRESHOLD = float(os.getenv("PHRASE_DISCOVERY_THRESHOLD", "0.55"))
MIN_PHRASE_SIM = float(os.getenv("MIN_PHRASE_SIM", "0.55"))

# Original PDF plain text stored in structured/chat_answers for JobBERT scoring.
RESUME_PLAIN_TEXT_KEY = "_resume_plain_text"

# resume_profiles.desired_role column limit (PostgreSQL VARCHAR).
DESIRED_ROLE_MAX_LEN = max(32, int(os.getenv("JOB_APP_DESIRED_ROLE_MAX_LEN", "255")))

# JWT для кабинета соискателя (users + resume_profiles в PostgreSQL).
_JWT_SECRET_RAW = os.getenv(
    "JOB_APP_JWT_SECRET",
    "dev-change-me-in-production-use-32chars-minimum!",
).strip()
JWT_SECRET = _resolve_jwt_secret(_JWT_SECRET_RAW)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = max(1, int(os.getenv("JOB_APP_JWT_EXPIRE_HOURS", "168")))

# Local cv.yml / cv.html preview while editing resume in chat.
CV_PREVIEW_DIR = Path(
    os.getenv("CV_PREVIEW_DIR", str(DATA_ROOT / "output" / "preview"))
).expanduser().resolve()
CV_PREVIEW_ENABLED = os.getenv("CV_PREVIEW_ENABLED", "1").strip().lower() in ("1", "true", "yes")

# Harvard HTML → Chrome/Chromium headless (--print-to-pdf).
CV_CHROME_BIN = os.getenv(
    "CV_CHROME_BIN",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
).strip()
CV_PDF_FILENAME = os.getenv("CV_PDF_FILENAME", "yevgen_cv.pdf").strip() or "yevgen_cv.pdf"

