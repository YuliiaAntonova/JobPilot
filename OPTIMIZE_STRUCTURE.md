# План оптимизации структуры JobPilot

Цель: понятные папки `frontend` / `backend`, без дублирования кода, утилиты отдельно, модели и I/O по слоям, ближе к SOLID. Без большого rewrite: сначала дубли и данные, потом папки.

## Как устроено сейчас

| Слой | Где лежит | Проблема |
|------|-----------|----------|
| Frontend | `frontend/` | почти ок, но `src/lib/` — свалка, страницы до 650 строк |
| Backend | `job_application/` | не `backend/`, внутри и API, и домен, и инфраструктура |
| CV workshop | `cv/` | отдельный остров, грузится через `importlib` (`cv_workshop.py`) |
| Статика | `job_application/static/app/` | артефакт Vite внутри backend |
| Данные | `data/`, `cv/yuliia_old/`, `job_application/output/` | runtime, PII и превью вперемешку |

Самые тяжёлые файлы:

- `job_application/resume/profile_text.py` — **4218** строк
- `job_application/resume/safe_tailoring/_core.py` — **2523** (ноутбук, не ядро)
- `job_application/resume/profile_service.py` — **742**
- `job_application/resume/cv_schema.py` — **629**
- `frontend/src/portal/NewOfferPage.jsx` — **651**
- `job_application/resume/safe_tailoring/orchestrator.py` — **593**

## Целевая раскладка

Имя Python-пакета (`job_application`) можно не менять сразу. `backend/` — корень кода; rename импортов — отдельный шаг.

```
agentic_rest_api_slim/
  frontend/                 # Vite SPA
    src/
      app/                  # router, shell
      pages/                # бывший portal/
      features/
        auth/
        resume/             # chat, view, tailor draft
        offers/             # JD, score, tracker
      shared/
        api/                # fetch, auth, timeouts
        ui/                 # Header, Footer, LlmModelSelect
        lib/                # textDiff, download — без домена
  backend/                  # пакет внутри можно оставить job_application
    api/                    # FastAPI routers + Pydantic DTO
    domain/
      cv/                   # schema, dates, yaml mapping
      profile/
      jobs/
    application/            # use-cases: parse PDF, score, tailor, export
    infra/
      db/                   # ORM, repositories
      llm/                  # один клиент
      pdf/                  # chromium + render
      rag/
    pipelines/
      tailor/               # ОДИН активный путь (crew_l7)
  data/
    input/                  # uploads (runtime, gitignore)
    output/                 # pdf/html/yml превью
    storage/                # rag indexes, jobs
  tests/
```

## Что дублируется (убрать в первую очередь)

### 1. Два `template_extractor.py` + два `cv_template.json`

`resume/crew_tailoring/` и `resume/rag_prepare/`. Один модуль: `domain/cv/template_shape.py`.

### 2. Три тейлоринга

- `crew_tailoring/` — основной (`TAILORING_PIPELINE=crew_l7`)
- `notebook_tailoring/` — legacy
- `safe_tailoring/_core.py` — 2500 строк из ноутбука

Оставить **один** публичный use-case (`run_analyze` / `run_generate`). Остальное за feature-flag, потом удалить.

### 3. CV в двух мирах

`cv/render.py` + `cv/pdf_to_yml_llm.py` подключаются динамически. Перенести в `backend/infra/pdf/` обычным импортом. `cv/yuliia_old/` — не код, а локальные файлы; в git не держать.

### 4. Два `ResumeProfile`

ORM в `models/db.py` и dataclass в `resume/profile_model.py` (circular import с `profile_service`). Разделить: `infra/db/models.py` vs `domain/profile/entity.py`.

### 5. Нормализация дат / experience

`cv_yml_io.py`, куски `cv_schema.py`, `documents/resume_normalize.py`, `cv_yaml.py`. Один `domain/cv/normalize.py` + `domain/cv/dates.py`.

### 6. LLM wrappers

Есть `shared/llm/client.py`, поверх ещё `notebook_tailoring/llm.py`, `rag_prepare/llm.py`, `safe_tailoring/_core.generate_response`. Один клиент + тонкие адаптеры (LlamaIndex / CrewAI).

### 7. Frontend ↔ backend schema

`resumeChat.js`: «sync with backend `cv_schema.py`». Поля cv.yml живут **только на бэке**; UI шлёт answers/JSON и не дублирует маппинг.

### 8. Пустые слои

`services/` — фасад на ~20 строк, `utils/` почти пустой, `routers/jobs.py` и `routers/profile.py` — re-export. Либо наполнить, либо удалить.

## SOLID

| Принцип | Сейчас | Как |
|---------|--------|-----|
| S | `profile_service`, `orchestrator`, `NewOfferPage` делают parse + persist + render + LLM | один файл = одна операция (from-chat, from-pdf, tailor, pdf-export) |
| O | новый пайплайн = ещё одна папка-копия | `TailorPipeline` protocol, реализация `CrewL7` |
| L | notebook/crew/safe с разным JSON | один `CvDocument` после `normalize_to_cv` |
| I | `analyze.py` реэкспортирует `_split_skills` | router только HTTP; парсинг в domain/forms |
| D | роутеры импортят CrewAI, Chrome, SQLAlchemy | router → service → infra |

`config.py` оставить тонким: env → typed settings (`pydantic-settings`), без бизнес-логики JWT.

`main.py`: `create_all` + ручной `ALTER TABLE` вынести в Alembic (`backend/infra/db/migrations/`).

## Input / output по папкам

Сейчас превью пишется в `cv/yuliia_old`, RAG в `data/rag_storage`, джобы в `data/jobs`, PDF рядом с репо.

Всё под `JOB_APP_DATA_ROOT`:

```
data/
  input/uploads/      # PDF резюме, JD файлы
  output/
    preview/          # cv.yml, cv.html, pdf (вместо cv/yuliia_old)
    tailored/         # черновики под вакансию
  storage/
    rag/              # llama indexes
    jobs/             # если ещё файлы, кроме Postgres
```

В git только `.gitkeep`. Persisted state — Postgres (`users`, `resume_profiles`, `application_jobs.outputs`).

DTO: `api/dto/` (`AuthIn`, `ChatAnswersIn`, `TailorGenerateIn`, `JobCreateIn`) отдельно от ORM.

## Frontend

```
pages/          Login, Home, Profile, ResumeChat, ResumeView, NewOffer, OfferReply, Saved
features/resume lib: resumeChat, sections, tailoredCvDraft
features/offers lib: offerDraft*, jdDraft, resumeJobPayload
shared/api      jobseekerProfile, fetchWithTimeout
```

`NewOfferPage.jsx` разрезать на: форма JD, блок score, блок tailor, side effects. Не тащить домен cv.yml в JS.

## Порядок работ (чтобы не сломать Docker/API)

### Фаза 0 — гигиена (1 PR, без смены URL)

- `.gitignore`: `cv/yuliia_old/`, персональные PDF, `data/**`
- удалить re-export routers, слить `template_extractor`
- `CV_PREVIEW_DIR` → `data/output/preview` (в Docker уже `/app/data/cv_preview`)

### Фаза 1 — один CV-домен

- `cv/render` + yaml I/O внутрь пакета
- `normalize_to_cv` — единственная точка входа
- разрезать `profile_text.py` на `chat_answers`, `plain_text`, `skills`, `experience`

### Фаза 2 — один tailor

- публичный API только через `orchestrator`
- `notebook_tailoring` + `_core.py` за флаг, затем delete
- usage/token logging в `infra/llm/usage.py`

### Фаза 3 — папки backend/api/domain/infra

- роутеры тонкие, сервисы без HTTP
- ORM отдельно от dataclass
- Alembic

### Фаза 4 — frontend features/

- только после стабильного `/profile` и `/analyze/resume-tailor`

Не начинать с `git mv job_application backend` — ломает импорты, тесты и Docker, а структуру не лечит.

## Чего не делать

- Не копировать cv-схему в OpenAPI «для красоты» и параллельно в JS.
- Не держать `job_application/static/app` в git как источник правды (только Vite outDir / Docker stage).
- Не смешивать локальный `.env` / БД `world` с шаблоном для других — это уже отделено.

## С чего начать

Фазы **0 + 1**: один `template_extractor`, превью в `data/output`, импорт `cv/` как нормального модуля — без смены публичных API.

## Статус (2026-11-25)

- [x] Фаза 0 — гигиена, template_extractor, preview dir, thin routers
- [x] Фаза 1 — `resume/pdf`, `normalize_to_cv`, split `profile_text/`
- [x] Фаза 2 — JobBERT вне `_core`, `infra/llm`, `ALLOW_LEGACY_TAILORING`, `pack_and_log_token_usage`
- [x] Фаза 3 (частично) — `domain/profile` (`ProfileEntity`), `infra/db` + `infra/llm` (без rename пакета)
- [x] Фаза 4 (частично) — `features/{resume,offers}/lib`, `shared/{api,lib}`, `pages/` + re-export stubs
- [x] Cover letter → `cover_letter/` (без notebook); Alembic baseline; NewOffer split
- [ ] Удалить `notebook_tailoring` / `_core` после отказа от legacy tailor
- [ ] Полный `backend/` rename — позже
