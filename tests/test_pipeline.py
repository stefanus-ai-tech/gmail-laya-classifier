import base64
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gmail_laya.classifier import classify, group_by_model
from gmail_laya.gmail import iter_messages
from gmail_laya.parser import parse_message


def encoded(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


class ParserTests(unittest.TestCase):
    def test_prefers_nested_plain_text_and_ignores_attachment(self):
        raw = {
            "id": "m1", "threadId": "t1", "internalDate": "123", "snippet": "Preview",
            "payload": {
                "headers": [{"name": "From", "value": "Alice <a@example.com>"},
                            {"name": "Subject", "value": "Invoice help"}],
                "parts": [{"mimeType": "multipart/alternative", "parts": [
                    {"mimeType": "text/html", "body": {"data": encoded("<p>HTML</p>")}},
                    {"mimeType": "text/plain", "body": {"data": encoded("Please check invoice")}},
                ]}, {"mimeType": "text/plain", "filename": "secret.txt",
                     "body": {"data": encoded("attachment text")}}],
            },
        }
        email = parse_message(raw)
        self.assertEqual(email.sender, "Alice <a@example.com>")
        self.assertEqual(email.subject, "Invoice help")
        self.assertEqual(email.body, "Please check invoice")
        self.assertEqual(email.received_at_ms, "123")

    def test_html_fallback_strips_script_and_snippet_fallback(self):
        raw = {"id": "m2", "snippet": "Preview &amp; more", "payload": {
            "parts": [{"mimeType": "text/html", "body": {
                "data": encoded("<p>Hello &amp; welcome</p><script>secret()</script>")}}]}}
        self.assertIn("Hello & welcome", parse_message(raw).body)
        self.assertNotIn("secret()", parse_message(raw).body)
        self.assertEqual(parse_message({"id": "m3", "snippet": "Fallback"}).body, "Fallback")


class ClassifierTests(unittest.TestCase):
    def test_calls_official_laya_email_interface_and_maps_result(self):
        email = parse_message({"id": "m1", "snippet": "Need a refund", "payload": {
            "headers": [{"name": "Subject", "value": "Payment"}]}})
        calls = []

        class FakeRouter:
            def predict(self, state, questions):
                calls.append((state, questions))
                return {"answers": {
                    "category": {"choice": "billing", "confidence": 0.91},
                    "is_spam": {"noul": 0.02}, "is_phishing": {"noul": 0.01},
                    "urgency": {"score": 1.2}, "needs_reply": {"noul": 0.8}},
                    "routing": {"model": "english"}}

        fake_laya = SimpleNamespace(
            email_state=lambda subject, body, sender: {
                "subject": subject, "body": body, "from": sender},
            email_questions=lambda: {"category": {"type": "choice"}},
        )
        record = classify(email, router=FakeRouter(), laya_module=fake_laya)
        self.assertEqual(calls[0][0]["body"], "Need a refund")
        self.assertEqual(calls[0][1]["category"]["type"], "choice")
        self.assertEqual(record["classification"]["category"], "billing")
        self.assertEqual(record["classification"]["routing"]["model"], "english")

    def test_groups_languages_without_changing_original_positions(self):
        emails = [parse_message({"id": key, "snippet": text}) for key, text in
                  [("a", "Hello"), ("b", "Halo"), ("c", "Thanks"), ("d", "Terima kasih")]]

        class FakeRouter:
            def route(self, state, questions):
                model = "multilingual" if state["body"] in {"Halo", "Terima kasih"} else "english"
                return SimpleNamespace(model=model)

        fake_laya = SimpleNamespace(
            email_state=lambda subject, body, sender: {"body": body},
            email_questions=lambda: {"category": {"type": "choice"}},
        )
        work = group_by_model(emails, FakeRouter(), fake_laya)
        self.assertEqual([index for _, index, _ in work], [0, 2, 1, 3])
        self.assertEqual([email.id for _, _, email in work], ["a", "c", "b", "d"])
        self.assertEqual([model for model, _, _ in work],
                         ["english", "english", "multilingual", "multilingual"])


class GmailListingTests(unittest.TestCase):
    def test_paginates_and_stops_at_limit(self):
        calls = []

        class Request:
            def __init__(self, value):
                self.value = value

            def execute(self):
                return self.value

        class Messages:
            def list(self, **kwargs):
                calls.append(("list", kwargs))
                if kwargs.get("pageToken"):
                    return Request({"messages": [{"id": "c"}]})
                return Request({"messages": [{"id": "a"}, {"id": "b"}],
                                "nextPageToken": "next"})

            def get(self, **kwargs):
                calls.append(("get", kwargs))
                return Request({"id": kwargs["id"]})

        service = SimpleNamespace(users=lambda: SimpleNamespace(messages=lambda: Messages()))
        self.assertEqual([m["id"] for m in iter_messages(service, "in:inbox", 3)],
                         ["a", "b", "c"])
        self.assertEqual(calls[0][1]["maxResults"], 3)
        self.assertEqual(calls[3][1]["maxResults"], 1)
        self.assertEqual(calls[3][1]["pageToken"], "next")


if __name__ == "__main__":
    unittest.main()
