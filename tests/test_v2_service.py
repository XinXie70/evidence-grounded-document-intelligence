import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
from fastapi.testclient import TestClient

from egdi.v2.llm import LlmResult
from egdi.v2.service.api import create_app
from egdi.v2.service.store import Store


def make_pdf(pages: list[str]) -> bytes:
    """A minimal valid PDF with one line of text per page (no parentheses in the text)."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, text in enumerate(pages):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {5 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>".encode()
        )
        stream = f"BT /F1 10 Tf 20 750 Td ({text}) Tj ET".encode()
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


TEXT = "The annual report states that total revenue for the year was 1200 million and operating costs were 900 million across all segments. "
PAGES = [TEXT + "Cover and contents.", TEXT + "Revenue grew 25 percent compared with the prior year driven by cloud subscriptions.", TEXT + "Appendix."]


class FakeEncoder:
    def split_text(self, text, chunk_tokens, overlap_tokens):
        words = text.split()
        return [" ".join(words[i : i + 8]) for i in range(0, len(words), 8)] or [""]

    def _embed(self, text):
        vector = np.zeros(32)
        for word in text.lower().split():
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 32] += 1
        return vector

    def encode_passages(self, texts):
        return np.array([self._embed(t) for t in texts])

    def encode_query(self, query):
        return self._embed(query)


def call(name, call_id, **arguments):
    item = {"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}
    return SimpleNamespace(**item, model_dump=lambda exclude_none=True, item=item: dict(item))


class ScriptedLlm:
    """Plays: search, read page 2, finish answered, regardless of the question."""

    def __init__(self, ledger=None, cost=0.01):
        self.ledger = ledger  # the real LlmClient adds each call's cost to the shared ledger
        self.turns = [
            [call("search_document", "1", query="revenue growth")],
            [call("read_pages", "2", pages=[2])],
            [call("finish", "3", status="answered", answer="Revenue grew 25 percent.", cited_pages=[2])],
        ]
        self.cost = cost

    def respond(self, **kwargs):
        output = self.turns.pop(0)
        if self.ledger is not None:
            self.ledger.add(self.cost)
        return LlmResult(SimpleNamespace(output=output), {"input_tokens": 100, "output_tokens": 10}, self.cost, 0.01)


class BrokenLlm:
    def respond(self, **kwargs):
        raise RuntimeError("model unavailable")


def build(tmp, llm_factory, **kw):
    return TestClient(create_app(Path(tmp), llm_factory=llm_factory, encoder_factory=FakeEncoder, **kw))


def upload(client, pages=PAGES, name="report.pdf"):
    return client.post(f"/documents?name={name}", content=make_pdf(pages), headers={"Content-Type": "application/pdf"})


class DocumentTests(unittest.TestCase):
    def test_upload_list_page_text_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = build(tmp, lambda ledger, log: ScriptedLlm(ledger))
            created = upload(client)
            self.assertEqual(created.status_code, 201)
            doc = created.json()
            self.assertEqual((doc["page_count"], doc["low_text_pages"], doc["existing"], doc["warnings"]), (3, 0, False, []))
            self.assertTrue(doc["id"].startswith("upload-"))
            again = upload(client).json()
            self.assertTrue(again["existing"])
            self.assertEqual(again["id"], doc["id"])
            self.assertEqual([d["name"] for d in client.get("/documents").json()], ["report.pdf"])
            page = client.get(f"/documents/{doc['id']}/pages/2").json()
            self.assertIn("cloud subscriptions", page["text"])
            self.assertEqual(client.get(f"/documents/{doc['id']}/pages/9").status_code, 404)
            self.assertEqual(client.get("/documents/nope").status_code, 404)

    def test_rejects_non_pdf_and_warns_about_pages_without_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = build(tmp, lambda ledger, log: ScriptedLlm(ledger))
            self.assertEqual(client.post("/documents", content=b"hello").status_code, 400)
            doc = upload(client, ["Hi", TEXT], name="scan.pdf").json()
            self.assertEqual(doc["low_text_pages"], 1)
            self.assertIn("1 of 2 pages", doc["warnings"][0])

    def test_ui_is_served(self):
        with tempfile.TemporaryDirectory() as tmp:
            response = build(tmp, None).get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Document Agent", response.text)


class QuestionTests(unittest.TestCase):
    def test_question_runs_the_agent_and_stores_the_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = build(tmp, lambda ledger, log: ScriptedLlm(ledger))
            doc_id = upload(client).json()["id"]
            accepted = client.post(f"/documents/{doc_id}/questions", json={"question": "How much did revenue grow?"})
            self.assertEqual(accepted.status_code, 202)
            task = client.get(f"/tasks/{accepted.json()['task_id']}").json()
            self.assertEqual(task["status"], "done")
            result = task["result"]
            self.assertEqual(result["final"], {"status": "answered", "answer": "Revenue grew 25 percent.", "cited_pages": [2]})
            self.assertEqual([s["tool"] for s in result["trace"]], ["search_document", "read_pages", "finish"])
            self.assertEqual(result["pages_read"], [2])
            self.assertAlmostEqual(task["cost_usd"], 0.03)
            self.assertAlmostEqual(client.get("/health").json()["spent_usd"], 0.03)
            self.assertEqual(len(client.get(f"/documents/{doc_id}/tasks").json()), 1)

    def test_validation_and_unknown_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = build(tmp, lambda ledger, log: ScriptedLlm(ledger))
            doc_id = upload(client).json()["id"]
            self.assertEqual(client.post(f"/documents/{doc_id}/questions", json={"question": ""}).status_code, 422)
            self.assertEqual(client.post(f"/documents/{doc_id}/questions", json={"question": "x" * 1001}).status_code, 422)
            self.assertEqual(client.post("/documents/nope/questions", json={"question": "hi"}).status_code, 404)
            self.assertEqual(client.get("/tasks/999").status_code, 404)

    def test_model_failure_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = build(tmp, lambda ledger, log: BrokenLlm())
            doc_id = upload(client).json()["id"]
            task_id = client.post(f"/documents/{doc_id}/questions", json={"question": "anything"}).json()["task_id"]
            task = client.get(f"/tasks/{task_id}").json()
            self.assertEqual(task["status"], "failed")
            self.assertIn("model unavailable", task["error"])

    def test_missing_api_key_gives_a_clear_failure(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            client = build(tmp, None)
            self.assertFalse(client.get("/health").json()["api_key_configured"])
            doc_id = upload(client).json()["id"]
            task_id = client.post(f"/documents/{doc_id}/questions", json={"question": "anything"}).json()["task_id"]
            self.assertIn("OPENAI_API_KEY is not set", client.get(f"/tasks/{task_id}").json()["error"])

    def test_spending_cap_blocks_new_questions_and_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = build(tmp, lambda ledger, log: ScriptedLlm(ledger, cost=0.01), max_total_usd=0.02)
            doc_id = upload(client).json()["id"]
            client.post(f"/documents/{doc_id}/questions", json={"question": "first"})  # costs 0.03 > cap
            self.assertEqual(client.post(f"/documents/{doc_id}/questions", json={"question": "second"}).status_code, 402)
            restarted = build(tmp, lambda ledger, log: ScriptedLlm(ledger), max_total_usd=0.02)
            self.assertAlmostEqual(restarted.get("/health").json()["spent_usd"], 0.03)
            self.assertEqual(restarted.post(f"/documents/{doc_id}/questions", json={"question": "third"}).status_code, 402)


class DeleteTests(unittest.TestCase):
    def test_delete_removes_files_and_questions_but_keeps_the_spend(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = build(tmp, lambda ledger, log: ScriptedLlm(ledger))
            doc_id = upload(client).json()["id"]
            client.post(f"/documents/{doc_id}/questions", json={"question": "How much did revenue grow?"})
            spent = client.get("/health").json()["spent_usd"]
            self.assertGreater(spent, 0)
            self.assertEqual(client.delete(f"/documents/{doc_id}").json(), {"deleted": doc_id})
            self.assertEqual(client.get("/documents").json(), [])
            self.assertEqual(client.get(f"/documents/{doc_id}").status_code, 404)
            self.assertEqual(client.get("/tasks/1").status_code, 404)
            self.assertFalse((Path(tmp) / "pages" / f"{doc_id}.jsonl").exists())
            self.assertFalse((Path(tmp) / "pdfs" / f"{doc_id}.pdf").exists())
            self.assertAlmostEqual(client.get("/health").json()["spent_usd"], spent)  # cap cannot be reset by deleting
            restarted = build(tmp, lambda ledger, log: ScriptedLlm(ledger))
            self.assertAlmostEqual(restarted.get("/health").json()["spent_usd"], spent)
            again = upload(client).json()  # the same file can be uploaded again from scratch
            self.assertFalse(again["existing"])
            self.assertEqual(client.get(f"/documents/{again['id']}/tasks").json(), [])

    def test_delete_unknown_or_busy_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = build(tmp, lambda ledger, log: ScriptedLlm(ledger))
            self.assertEqual(client.delete("/documents/nope").status_code, 404)
            doc_id = upload(client).json()["id"]
            store = Store(Path(tmp) / "service.sqlite3")
            task = store.create_task(doc_id, "still running")
            store.mark_running(task)
            self.assertEqual(client.delete(f"/documents/{doc_id}").status_code, 409)
            self.assertEqual(client.get(f"/documents/{doc_id}").status_code, 200)


class StoreTests(unittest.TestCase):
    def test_unfinished_tasks_are_marked_failed_on_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.sqlite3"
            store = Store(path)
            store.add_document("d", "n.pdf", "sha", 3, 0)
            running = store.create_task("d", "q1")
            store.mark_running(running)
            queued = store.create_task("d", "q2")
            finished = store.create_task("d", "q3")
            store.finish_task(finished, status="done", result={"x": 1}, cost_usd=0.5)
            reopened = Store(path)
            self.assertEqual(reopened.get_task(running)["status"], "failed")
            self.assertEqual(reopened.get_task(queued)["status"], "failed")
            self.assertEqual(reopened.get_task(finished)["status"], "done")
            self.assertEqual(reopened.get_task(finished)["result"], {"x": 1})
            self.assertAlmostEqual(reopened.total_cost(), 0.5)


if __name__ == "__main__":
    unittest.main()
