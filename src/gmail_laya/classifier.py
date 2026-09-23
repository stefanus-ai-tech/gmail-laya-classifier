"""Thin adapter around Laya's documented email API."""

from collections import defaultdict

from .parser import Email


def group_by_model(emails: list[Email], router, laya_module) -> list[tuple[int, Email]]:
    """Keep each language checkpoint hot while classifying a fetched batch."""
    groups = defaultdict(list)
    questions = laya_module.email_questions()
    for index, email in enumerate(emails):
        state = laya_module.email_state(email.subject, email.body, sender=email.sender)
        model = router.route(state, questions).model
        groups[model].append((index, email))
    return [item for group in groups.values() for item in group]


def classify(email: Email, router=None, laya_module=None) -> dict:
    if laya_module is None:
        import laya as laya_module
    if router is None:
        router = laya_module.Router()

    state = laya_module.email_state(email.subject, email.body, sender=email.sender)
    result = router.predict(state, laya_module.email_questions())
    answers = result["answers"]
    category = answers["category"]
    return {
        **email.to_dict(),
        "classification": {
            "category": category.get("choice"),
            "confidence": category.get("confidence"),
            "is_spam": answers.get("is_spam", {}).get("noul"),
            "is_phishing": answers.get("is_phishing", {}).get("noul"),
            "urgency": answers.get("urgency", {}).get("score"),
            "needs_reply": answers.get("needs_reply", {}).get("noul"),
            "routing": result.get("routing", {}),
        },
    }
