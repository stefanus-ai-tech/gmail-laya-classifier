"""Extract useful text from Gmail's full message format."""

import base64
import binascii
import html
import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"br", "p", "div", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _decode(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
            "utf-8", errors="replace"
        )
    except (ValueError, UnicodeError, binascii.Error):
        return ""


def _parts(payload):
    yield payload
    for part in payload.get("parts", []):
        yield from _parts(part)


def _body(payload, snippet):
    parts = list(_parts(payload))
    for mime in ("text/plain", "text/html"):
        for part in parts:
            if part.get("filename") or part.get("mimeType") != mime:
                continue
            data = part.get("body", {}).get("data")
            if not data:
                continue
            content = _decode(data)
            if mime == "text/html":
                parser = _HTMLText()
                parser.feed(content)
                content = html.unescape("".join(parser.parts))
            content = re.sub(r"[ \t]+", " ", content).strip()
            if content:
                return content[:12000]
    return snippet[:12000]


@dataclass(frozen=True)
class Email:
    id: str
    thread_id: str
    sender: str
    subject: str
    snippet: str
    body: str
    received_at_ms: str

    def to_dict(self):
        return asdict(self)


def parse_message(message: dict) -> Email:
    payload = message.get("payload") or {}
    headers = {
        h.get("name", "").lower(): h.get("value", "")
        for h in payload.get("headers", [])
    }
    snippet = html.unescape(message.get("snippet") or "")
    return Email(
        id=message["id"],
        thread_id=message.get("threadId", ""),
        sender=headers.get("from", ""),
        subject=headers.get("subject", ""),
        snippet=snippet,
        body=_body(payload, snippet),
        received_at_ms=message.get("internalDate", ""),
    )
