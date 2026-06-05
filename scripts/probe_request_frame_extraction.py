"""RequestFrame Extraction Benchmark — the missing bridge from phrase to resolver.

Tests: given a user phrase, can we correctly extract:
  operation_hint, resource_kind_hint, connector_hint
This is the step BEFORE discovery/resolver/authority in production.
"""

from __future__ import annotations

from dataclasses import dataclass

# ─── EXTRACTION ENGINE ────────────────────────────────────────────

# Maps action verbs to operations
VERB_TO_OPERATION = {
    "create": "create",
    "add": "create",
    "make": "create",
    "schedule": "create",
    "book": "book",
    "reserve": "book",
    "list": "list",
    "show": "list",
    "find": "search",
    "search": "search",
    "get": "read",
    "read": "read",
    "fetch": "read",
    "view": "read",
    "check": "read",
    "update": "update",
    "edit": "update",
    "change": "update",
    "modify": "update",
    "delete": "delete",
    "remove": "delete",
    "cancel": "delete",
    "send": "send",
    "post": "send",
    "push": "send",
    "upload": "upload",
    "download": "download",
    "export": "export",
    "generate": "export",
    "summarize": "summarize",
    "translate": "translate",
    "classify": "classify",
    "use": "list",  # "use X" defaults to list
}

# Maps domain nouns to resource_kind
NOUN_TO_DOMAIN = {
    "calendar": "calendar_event",
    "event": "calendar_event",
    "events": "calendar_event",
    "appointment": "appointment",
    "appointments": "appointment",
    "task": "task",
    "tasks": "task",
    "todo": "task",
    "reminder": "reminder",
    "reminders": "reminder",
    "alert": "reminder",
    "note": "note",
    "notes": "note",
    "contact": "contact",
    "contacts": "contact",
    "message": "message",
    "messages": "message",
    "chat": "message",
    "file": "file",
    "files": "file",
    "document": "document",
    "documents": "document",
    "email": "email_message",
    "mail": "email_message",
    "payment": "payment",
    "subscription": "subscription",
    "report": "report",
    "analytics": "analytics_query",
    "notification": "notification",
    "workflow": "workflow",
    "profile": "profile",
    "search": "search_query",
    "flight": "travel_booking",
    "ride": "travel_booking",
}

# Maps service names to connector hints
SERVICE_TO_CONNECTOR = {
    "familyos": "familyos",
    "google": "google",
    "microsoft": "microsoft",
    "apple": "apple",
    "amazon": "amazon",
    "meta": "meta",
    "spotify": "spotify",
    "uber": "uber",
    "airbnb": "airbnb",
    "slack": "slack",
    "notion": "notion",
    "todoist": "todoist",
    "salesforce": "salesforce",
    "hubspot": "hubspot",
    "shopify": "shopify",
    "stripe": "stripe",
    "twilio": "twilio",
    "sendgrid": "sendgrid",
    "datadog": "datadog",
    "splunk": "splunk",
    "github": "github",
    "gitlab": "gitlab",
    "atlassian": "atlassian",
    "jira": "jira",
    "zoom": "zoom",
    "teams": "teams",
    "discord": "discord",
    "telegram": "telegram",
    "whatsapp": "whatsapp",
    "reddit": "reddit",
    "linkedin": "linkedin",
    "pinterest": "pinterest",
    "yelp": "yelp",
    "strava": "strava",
    "dropbox": "dropbox",
    "box": "box",
    "figma": "figma",
    "canva": "canva",
    "zendesk": "zendesk",
    "servicenow": "servicenow",
    "workday": "workday",
    "oracle": "oracle",
    "ibm": "ibm",
    "sap": "sap",
    "monday": "monday",
    "clickup": "clickup",
    "linear": "linear",
    "height": "height",
    "coda": "coda",
    "airtable": "airtable",
    "notability": "notability",
}


@dataclass
class ExtractionResult:
    phrase: str
    operation_hint: str
    resource_kind_hint: str | None
    connector_hint: str | None
    # Ground truth
    expected_operation: str
    expected_domain: str
    expected_connector: str
    expected_verdict: str
    # Correctness
    operation_correct: bool
    resource_correct: bool
    connector_correct: bool
    all_correct: bool
    tier: str = ""


def extract_from_phrase(phrase: str) -> tuple[str, str | None, str | None]:
    """Extract operation_hint, resource_kind_hint, connector_hint from a user phrase."""
    words = phrase.lower().split()
    # Remove punctuation
    words = [w.strip(".,!?;:\"'()[]{}") for w in words]

    # Operation: first matching verb
    operation = "list"  # default
    for w in words:
        if w in VERB_TO_OPERATION:
            operation = VERB_TO_OPERATION[w]

    # Resource kind: first matching domain noun
    resource_kind = None
    for w in words:
        if w in NOUN_TO_DOMAIN:
            resource_kind = NOUN_TO_DOMAIN[w]
            break

    # Connector: first matching service name
    connector = None
    for w in words:
        if w in SERVICE_TO_CONNECTOR:
            connector = SERVICE_TO_CONNECTOR[w]
            break
    # If connector hint found but no explicit domain, try to infer
    if connector and not resource_kind:
        for w in words:
            if w in NOUN_TO_DOMAIN:
                resource_kind = NOUN_TO_DOMAIN[w]
                break

    return operation, resource_kind, connector


# ─── GOLDEN TEST SET ──────────────────────────────────────────────


@dataclass
class ExtractionQuery:
    phrase: str
    expected_operation: str
    expected_domain: str
    expected_connector: str  # connector prefix, e.g. "google.calendar"
    expected_verdict: str
    tier: str


def build_extraction_test_set() -> list[ExtractionQuery]:
    queries = []

    # Exact: "Create a google calendar event"
    connectors = [
        "google.calendar",
        "familyos.calendar",
        "microsoft.tasks",
        "apple.reminders",
        "slack.messages",
        "notion.documents",
        "github.files",
        "stripe.payments",
        "zooms.meetings",
        "dropbox.files",
        "figma.documents",
        "airtable.tasks",
        "todoist.tasks",
        "salesforce.reports",
        "hubspot.contacts",
    ]

    for cid in connectors:
        ns, domain = cid.split(".")
        op = "create"
        queries.append(
            ExtractionQuery(
                phrase=f"Create a {ns} {domain} event",
                expected_operation=op,
                expected_domain=domain_to_rk(domain),
                expected_connector=cid,
                expected_verdict="can_bind",
                tier="easy",
            )
        )

    # Operation variety
    ops = [
        ("List my {ns} {domain}s", "list"),
        ("Delete the {ns} {domain}", "delete"),
        ("Update {ns} {domain}", "update"),
        ("Search {ns} {domain}s", "search"),
        ("Check {ns} {domain}s", "read"),
        ("Export {ns} {domain} report", "export"),
    ]
    for phrase_tmpl, op in ops:
        for cid in connectors[:5]:
            ns, domain = cid.split(".")
            queries.append(
                ExtractionQuery(
                    phrase=phrase_tmpl.format(ns=ns, domain=domain),
                    expected_operation=op,
                    expected_domain=domain_to_rk(domain),
                    expected_connector=cid,
                    expected_verdict="can_bind",
                    tier="easy",
                )
            )

    # Ambiguous: no connector in phrase
    ambig_phrases = [
        ("Create a calendar event", "create", "calendar_event"),
        ("List my tasks", "list", "task"),
        ("Set a reminder for tomorrow", "create", "reminder"),
        ("Send a message", "send", "message"),
        ("Book an appointment", "book", "appointment"),
        ("Upload a file", "upload", "file"),
        ("Search documents", "search", "document"),
        ("Check notifications", "read", "notification"),
        ("Generate a report", "export", "report"),
        ("Delete a task", "delete", "task"),
    ]
    for phrase, op, rk in ambig_phrases:
        for _ in range(5):
            queries.append(
                ExtractionQuery(
                    phrase=phrase,
                    expected_operation=op,
                    expected_domain=rk,
                    expected_connector="",
                    expected_verdict="needs_disambiguation",
                    tier="hard",
                )
            )

    # Pad to 200
    while len(queries) < 200:
        cid = connectors[len(queries) % len(connectors)]
        ns, domain = cid.split(".")
        queries.append(
            ExtractionQuery(
                phrase=f"Use {ns} {domain}",
                expected_operation="list",
                expected_domain=domain_to_rk(domain),
                expected_connector=cid,
                expected_verdict="can_bind",
                tier="easy",
            )
        )

    return queries[:200]


def domain_to_rk(domain: str) -> str:
    NOUN_TO_DOMAIN_REVERSE = {
        "calendar": "calendar_event",
        "tasks": "task",
        "reminders": "reminder",
        "notes": "note",
        "contacts": "contact",
        "messages": "message",
        "files": "file",
        "email": "email_message",
        "appointments": "appointment",
        "reservations": "reservation",
        "payments": "payment",
        "subscriptions": "subscription",
        "analytics": "analytics_query",
        "notifications": "notification",
        "search": "search_query",
        "profiles": "profile",
        "reports": "report",
        "workflows": "workflow",
        "documents": "document",
        "chats": "chat_message",
    }
    return NOUN_TO_DOMAIN_REVERSE.get(domain, domain)


def evaluate_extraction(query: ExtractionQuery) -> ExtractionResult:
    op, rk, conn = extract_from_phrase(query.phrase)

    op_correct = op == query.expected_operation
    rk_correct = rk == query.expected_domain
    conn_correct = (
        conn == query.expected_connector.split(".")[0] if query.expected_connector else conn is None
    )

    return ExtractionResult(
        phrase=query.phrase,
        operation_hint=op,
        resource_kind_hint=rk,
        connector_hint=conn,
        expected_operation=query.expected_operation,
        expected_domain=query.expected_domain,
        expected_connector=query.expected_connector,
        expected_verdict=query.expected_verdict,
        operation_correct=op_correct,
        resource_correct=rk_correct,
        connector_correct=conn_correct,
        all_correct=op_correct and rk_correct and conn_correct,
        tier=query.tier,
    )


def main() -> int:
    queries = build_extraction_test_set()
    results = [evaluate_extraction(q) for q in queries]

    n = len(results)
    op_acc = sum(1 for r in results if r.operation_correct) / n
    rk_acc = sum(1 for r in results if r.resource_correct) / n
    conn_acc = sum(1 for r in results if r.connector_correct) / n
    all_acc = sum(1 for r in results if r.all_correct) / n

    # Show failures
    failures = [r for r in results if not r.all_correct]

    print(f"{'='*60}")
    print(f"RequestFrame Extraction Benchmark — {n} phrases")
    print(f"{'='*60}")
    print(f"  Operation accuracy:   {op_acc:.1%}")
    print(f"  Resource accuracy:    {rk_acc:.1%}")
    print(f"  Connector accuracy:   {conn_acc:.1%}")
    print(f"  All three correct:    {all_acc:.1%}")
    print(f"  Failures:             {len(failures)}/{n}")
    print()

    if failures:
        print("--- Top 10 Failures ---")
        for f in failures[:10]:
            print(f'  Phrase: "{f.phrase}"')
            print(
                f"    Expected: op={f.expected_operation} rk={f.expected_domain} conn={f.expected_connector}"
            )
            print(
                f"    Got:      op={f.operation_hint} rk={f.resource_kind_hint} conn={f.connector_hint}"
            )
            wrong_parts = []
            if not f.operation_correct:
                wrong_parts.append("operation")
            if not f.resource_correct:
                wrong_parts.append("resource_kind")
            if not f.connector_correct:
                wrong_parts.append("connector")
            print(f"    Wrong: {', '.join(wrong_parts) if wrong_parts else 'none'}")

    print("\n--- By Tier ---")
    for tier in ["easy", "hard"]:
        subset = [r for r in results if r.tier == tier]
        if subset:
            sn = len(subset)
            print(
                f"  {tier} ({sn}): op={sum(1 for r in subset if r.operation_correct)/sn:.1%} "
                f"rk={sum(1 for r in subset if r.resource_correct)/sn:.1%} "
                f"conn={sum(1 for r in subset if r.connector_correct)/sn:.1%} "
                f"all={sum(1 for r in subset if r.all_correct)/sn:.1%}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
