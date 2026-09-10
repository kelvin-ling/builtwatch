"""Evidence and dependency checks; never turn model failures into user action items."""

from __future__ import annotations

import re

from .models import Finding, SystemPassport

# Bump whenever an assessment rule changes in a way that would alter past verdicts.
#
# This does two things at once, and both are required. It is mixed into the assessment
# cache key, so a bump forces every pair to be re-assessed instead of being skipped as
# already-seen; and findings stamped with an older version stop being served as current,
# so a rule fix actually retracts the findings it would no longer make. Fixing the code
# alone never withdrew anything.
#
# v4: affected-product test became evidence-driven and allowlist-free; assertions of
#     undeclared dependencies are now rejected as ungrounded.
QUALITY_VERSION = 4

# Shorter runs of characters are initials and articles, not product names.
MIN_TERM_LENGTH = 3

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


# Words that appear in almost every stack description and therefore prove nothing about
# applicability. Matching on these would make the affected-product test meaningless.
GENERIC_TERMS = frozenset(
    {
        "api", "apis", "sdk", "app", "apps", "cloud", "web", "data", "system", "systems",
        "service", "services", "server", "servers", "update", "updates", "change",
        "changes", "related", "agent", "agents", "platform", "software", "tool", "tools",
        "site", "sites", "user", "users", "account", "accounts", "database", "storage",
        "integration", "framework", "library", "runtime", "version", "release",
        # Security and regulatory boilerplate. These appear in the *names of sources we
        # monitor* ("CISA Known Exploited Vulnerabilities", "EU AI Act"), and matching on
        # them made every advisory look like a declared dependency.
        "vulnerability", "vulnerabilities", "exploited", "exploit", "known", "security",
        "advisory", "advisories", "act", "article", "policy", "policies", "regulation",
        "law", "laws", "guidance", "requirement", "requirements", "compliance",
    }
)

# Phrasings a model reaches for when it asserts the system depends on something. Group 1
# captures the thing claimed to be used.
_USAGE_CLAIM = re.compile(
    r"\b(?:the\s+)?(?:system|app|application|service|it)\s+"
    r"(?:uses|use|is\s+using|runs\s+on|runs|relies\s+on|depends\s+on|is\s+built\s+on|"
    r"is\s+running|deploys|hosts)\s+(.{3,60}?)(?:[,.;:]|$)",
    re.IGNORECASE,
)


def _tokens(text: str) -> set[str]:
    """Split text into comparable whole-word tokens, dropping vocabulary that proves nothing.

    Whole tokens, never substrings. Substring matching silently produced false applicability:
    "act" (from "EU AI Act") matched "actively exploited", and "aws" matches "laws".
    """
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9+.#-]*", text.lower())
        if len(token) >= MIN_TERM_LENGTH and token not in GENERIC_TERMS
    }


def declared_terms(passport: SystemPassport) -> set[str]:
    """Meaningful tokens naming what this system is actually built from."""
    return _tokens(" ".join(passport.technologies + passport.services))


def affected_product_undeclared(passport: SystemPassport, evidence_text: str) -> bool:
    """True when a vulnerability disclosure never names anything this system declares.

    This is the general form of the affected-product test and needs no allowlist. A
    security advisory is relevant to a system only if that system's declared stack appears
    in the advisory itself. If nothing declared is named, the applicability claim rests on
    the model's imagination rather than on the evidence.

    Deliberately evidence-driven rather than title-driven: the model writes the title, so
    testing the title would test the model's own words against itself.
    """
    # A passport declaring nothing specific gets no free pass. You cannot establish that
    # an advisory affects a system you know nothing about, so the claim is not supportable.
    return not (declared_terms(passport) & _tokens(evidence_text))


def unsupported_usage_claims(passport: SystemPassport, statements: list[str]) -> list[str]:
    """Assertions that the system uses something its passport never mentions.

    Catches the fabrication class directly: an inference like "The system uses Microsoft
    Windows" against a passport listing only Strands, the AWS SDK and Cloudflare Workers.
    Model-agnostic and source-agnostic, so it holds for products no allowlist anticipates.
    """
    terms = declared_terms(passport)
    unsupported: list[str] = []
    for statement in statements:
        for claimed in _USAGE_CLAIM.findall(statement):
            tokens = _tokens(claimed)
            # A claim naming nothing specific is vague, not fabricated - leave it alone.
            if tokens and not (tokens & terms):
                unsupported.append(claimed.strip())
    return unsupported


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
        re.search(
            r"Downgraded automatically|could not verify the suggested connection|"
            r"not found verbatim|cited snapshot|snap_[a-f0-9]+",
            x,
            re.IGNORECASE,
        )
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
