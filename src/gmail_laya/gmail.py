"""Gmail OAuth and read-only message retrieval."""

from pathlib import Path
from time import perf_counter

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def create_service(credentials_path: Path, token_path: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        # Never silently reuse a token granted broader Gmail access.
        if set(creds.scopes or []) != set(SCOPES):
            raise ValueError("token.json has unexpected Gmail scopes; remove it and reauthorize")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.is_file():
                raise FileNotFoundError(f"OAuth Desktop App credentials missing: {credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def iter_messages(service, query: str, limit: int, on_fetch=None, on_list=None):
    """Yield full Gmail messages, traversing list pages up to limit."""
    remaining = limit
    page_token = None
    while remaining > 0:
        params = {"userId": "me", "q": query, "maxResults": min(remaining, 500)}
        if page_token:
            params["pageToken"] = page_token
        started = perf_counter()
        page = service.users().messages().list(**params).execute()
        if on_list:
            on_list(perf_counter() - started, len(page.get("messages", [])))
        items = page.get("messages", [])
        for item in items:
            started = perf_counter()
            message = service.users().messages().get(
                userId="me", id=item["id"], format="full"
            ).execute()
            if on_fetch:
                on_fetch(item["id"], perf_counter() - started)
            yield message
            remaining -= 1
            if remaining == 0:
                return
        page_token = page.get("nextPageToken")
        if not page_token or not items:
            return
