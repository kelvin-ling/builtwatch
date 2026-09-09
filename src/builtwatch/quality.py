"""Evidence and dependency checks; never turn model failures into user action items."""

from __future__ import annotations

import re

from .models import Finding, SystemPassport

PRODUCTS = {
    "windows": ("windows",),
    "exchange server": ("exchange",),
    "sharepoint": ("sharepoint",),
    "fortinet": ("fortinet", "fortios"),
    "citrix": ("citrix",),
    "vmware": ("vmware",),
    "cisco": ("cisco",),
}
VENDORS = {
    "stripe-upgrades": ("stripe",),
    "twilio-changelog": ("twilio",),
    "github-rest-breaking": ("github api", "github rest", "github actions", "github"),
    "anthropic-aup": ("anthropic", "claude"),
    "aws-bedrock-history": ("bedrock", "nova"),
}


def dependency_mismatch(passport: SystemPassport, text: str) -> bool:
    """Named product vulnerabilities cannot inherit applicability from generic 'security'."""
    declared = " ".join(passport.technologies + passport.services).lower()
    text = text.lower()
    mentioned = [aliases for name, aliases in PRODUCTS.items() if name in text]
    return bool(mentioned) and not any(
        alias in declared for aliases in mentioned for alias in aliases
    )


def source_out_of_scope(passport: SystemPassport, source_id: str) -> bool:
    aliases = VENDORS.get(source_id)
    declared = " ".join(passport.technologies + passport.services).lower()
    return bool(aliases) and not any(alias in declared for alias in aliases)


def unverified(finding: Finding) -> bool:
    return bool(finding.validation_issues) or any(
        re.search(r"Downgraded automatically|not found verbatim|cited snapshot|snap_[a-f0-9]+", x)
        for x in finding.unknowns
    )


def friendly_failure(reason: str | None) -> str | None:
    if not reason:
        return reason
    if any(x in reason.lower() for x in ("ceiling", "allowance", "budget")):
        return (
            "The paid-check allowance was reached. "
            "Completed results are saved; the demo remains available."
        )
    return (
        "This check could not finish reliably. Completed results are saved; coverage is incomplete."
    )
