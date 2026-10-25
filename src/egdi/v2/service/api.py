"""FastAPI service: upload a PDF, ask a question, read back the answer and the agent's trace.

Local demo service: no authentication, so it binds to 127.0.0.1 by default. The agent, tools,
prompts and limits are the frozen V2 ones; this module only wires them to HTTP and SQLite.
"""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from typing import Any, Callable

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from egdi.corpus import extract_pdf_page_records, read_page_records_jsonl, write_page_records_jsonl
from egdi.v2.agent import Agent, AgentLimits
from egdi.v2.index import MODEL_CACHE, DocumentIndex, shared_encoder
from egdi.v2.llm import BudgetExceeded, CostLedger, LlmClient, load_config

MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_PAGES = 400
MAX_QUESTION_CHARS = 1000
UI_PATH = Path(__file__).with_name("ui.html")


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


def create_app(
    data_dir: Path,
    *,
    root: Path = Path("."),
    llm_factory: Callable[[CostLedger, Path], Any] | None = None,
    encoder_factory: Callable[[], Any] | None = None,
    max_total_usd: float = 5.0,
    limits: AgentLimits = AgentLimits(),
    max_concurrent: int = 2,
) -> FastAPI:
    from .store import Store  # local import keeps `import api` cheap

    data_dir.mkdir(parents=True, exist_ok=True)
    store = Store(data_dir / "service.sqlite3")
    ledger = CostLedger(max_total_usd)
    ledger.spent = store.total_cost()  # the cap survives restarts
    slots = threading.Semaphore(max_concurrent)
    build_lock = threading.Lock()
    indexes: dict[str, DocumentIndex] = {}
    llm_box: list[Any] = []

    def make_llm() -> Any:
        if not llm_box:
            if llm_factory is not None:
                llm_box.append(llm_factory(ledger, data_dir / "requests.jsonl"))
            else:
                if not os.environ.get("OPENAI_API_KEY"):
                    raise RuntimeError("OPENAI_API_KEY is not set")
                config, pricing = load_config(root)
                llm_box.append(LlmClient(config, pricing, ledger, log_path=data_dir / "requests.jsonl"))
        return llm_box[0]

    def get_index(doc_id: str) -> DocumentIndex:
        with build_lock:
            if doc_id not in indexes:
                records = read_page_records_jsonl(data_dir / "pages" / f"{doc_id}.jsonl")
                encoder = encoder_factory() if encoder_factory else shared_encoder(str(root / MODEL_CACHE))
                indexes[doc_id] = DocumentIndex(records, encoder)
            return indexes[doc_id]

    def run_task(task_id: int, doc_id: str, question: str) -> None:
        with slots:
            store.mark_running(task_id)
            try:
                result = Agent(make_llm(), limits).run(question, get_index(doc_id), f"service:{task_id}")
            except BudgetExceeded as error:
                store.finish_task(task_id, status="failed", error=f"service spending cap reached ({error})")
            except Exception as error:  # surfaced to the user; never crashes the worker thread
                store.finish_task(task_id, status="failed", error=f"{type(error).__name__}: {error}")
            else:
                store.finish_task(task_id, status="done", result=result, cost_usd=result["cost_usd"])

    app = FastAPI(title="Evidence-grounded document agent", version="2.0")

    @app.get("/")
    def ui() -> FileResponse:
        return FileResponse(UI_PATH, media_type="text/html")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "api_key_configured": bool(os.environ.get("OPENAI_API_KEY")) or llm_factory is not None,
            "spent_usd": round(ledger.spent, 4),
            "cap_usd": ledger.max_usd,
        }

    @app.post("/documents", status_code=201)
    async def upload(request: Request, name: str = "document.pdf") -> dict[str, Any]:
        body = await request.body()
        if not body.startswith(b"%PDF"):
            raise HTTPException(400, "body must be a PDF file (send the raw bytes with ?name=file.pdf)")
        if len(body) > MAX_PDF_BYTES:
            raise HTTPException(413, f"PDF larger than {MAX_PDF_BYTES // 2**20} MB")
        sha = hashlib.sha256(body).hexdigest()
        existing = store.find_by_sha(sha)
        if existing:
            return {**existing, "existing": True, "warnings": _warnings(existing)}
        doc_id = f"upload-{sha[:16]}"

        def process() -> dict[str, Any]:
            pdf_path = data_dir / "pdfs" / f"{doc_id}.pdf"
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(body)
            try:
                records = extract_pdf_page_records(pdf_path, doc_id)
            except Exception as error:
                pdf_path.unlink(missing_ok=True)
                raise HTTPException(422, f"could not read this PDF: {error}") from error
            if not records or len(records) > MAX_PAGES:
                pdf_path.unlink(missing_ok=True)
                raise HTTPException(422, f"PDF must have between 1 and {MAX_PAGES} pages")
            write_page_records_jsonl(data_dir / "pages" / f"{doc_id}.jsonl", records)
            low = sum(r.extraction_status != "ok" for r in records)
            return store.add_document(doc_id, name[:200], sha, len(records), low)

        document = await run_in_threadpool(process)
        return {**document, "existing": False, "warnings": _warnings(document)}

    @app.get("/documents")
    def documents() -> list[dict[str, Any]]:
        return store.list_documents()

    @app.get("/documents/{doc_id}")
    def document(doc_id: str) -> dict[str, Any]:
        found = store.get_document(doc_id)
        if not found:
            raise HTTPException(404, "unknown document")
        return {**found, "warnings": _warnings(found)}

    @app.get("/documents/{doc_id}/pages/{page}")
    def page_text(doc_id: str, page: int) -> dict[str, Any]:
        if not store.get_document(doc_id):
            raise HTTPException(404, "unknown document")
        records = read_page_records_jsonl(data_dir / "pages" / f"{doc_id}.jsonl")
        for record in records:
            if record.page == page:
                return {"page": page, "text": record.text, "extraction_status": record.extraction_status}
        raise HTTPException(404, "page out of range")

    @app.post("/documents/{doc_id}/questions", status_code=202)
    def ask(doc_id: str, body: QuestionRequest, background: BackgroundTasks) -> dict[str, Any]:
        if not store.get_document(doc_id):
            raise HTTPException(404, "unknown document")
        if ledger.spent >= ledger.max_usd:
            raise HTTPException(402, f"service spending cap of ${ledger.max_usd:.2f} reached")
        question = body.question.strip()
        if not question:
            raise HTTPException(422, "question is empty")
        task_id = store.create_task(doc_id, question)
        background.add_task(run_task, task_id, doc_id, question)
        return {"task_id": task_id, "status": "queued"}

    @app.get("/documents/{doc_id}/tasks")
    def tasks(doc_id: str) -> list[dict[str, Any]]:
        if not store.get_document(doc_id):
            raise HTTPException(404, "unknown document")
        return store.list_tasks(doc_id)

    @app.get("/tasks/{task_id}")
    def task(task_id: int) -> dict[str, Any]:
        found = store.get_task(task_id)
        if not found:
            raise HTTPException(404, "unknown task")
        return found

    return app


def _warnings(document: dict[str, Any]) -> list[str]:
    if document["low_text_pages"]:
        return [
            f"{document['low_text_pages']} of {document['page_count']} pages have little or no text layer "
            "(scans, charts, images). This agent reads text only; questions that depend on those pages will be answered as insufficient evidence."
        ]
    return []


def main() -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/derived/v2_service"))
    parser.add_argument("--max-total-usd", type=float, default=5.0, help="spending cap across all questions, kept across restarts")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(args.data_dir, max_total_usd=args.max_total_usd), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
