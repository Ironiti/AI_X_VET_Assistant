import re


REQUIRED_MONTHLY_METRICS_RECIPIENTS = (
    "boss@ai-agentix.by",
    "fin@ai-agentix.by",
    "operations@ai-agentix.by",
)


def merge_monthly_metrics_recipients(configured_recipients: str | None) -> str:
    """Preserve configured recipients and append mandatory monthly-report addresses."""
    recipients = []
    seen = set()

    for recipient in re.split(r"[,;]", configured_recipients or ""):
        normalized = recipient.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            recipients.append(normalized)
            seen.add(key)

    for recipient in REQUIRED_MONTHLY_METRICS_RECIPIENTS:
        key = recipient.casefold()
        if key not in seen:
            recipients.append(recipient)
            seen.add(key)

    return ", ".join(recipients)
