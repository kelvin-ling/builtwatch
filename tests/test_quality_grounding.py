"""Regressions for the fabricated-dependency class of defect.

A published finding once asserted "The system uses Microsoft Windows" against a passport
listing only Strands, the AWS SDK and Cloudflare Workers, citing a *monitored source* as
though it were a dependency. It passed validation because the evidence was verbatim and
the cited passport key existed. Neither check asks whether the fact supports the claim.

The first fix was a seven-product allowlist, which left Linux, OpenSSL, Log4j, Kubernetes
and nginx wide open. These tests pin the general behaviour instead.
"""

from __future__ import annotations

import pytest

from builtwatch.models import SystemPassport
from builtwatch.quality import (
    QUALITY_VERSION,
    affected_product_undeclared,
    declared_terms,
    unsupported_usage_claims,
)

WINDOWS_ADVISORY = (
    "Microsoft Windows Heap-Based Buffer Overflow Vulnerability: Microsoft Windows "
    "Advanced Local Procedure Call contains a heap-based buffer overflow vulnerability "
    "that allows an attacker to elevate privileges locally."
)


@pytest.fixture
def builtwatch_passport() -> SystemPassport:
    """The real passport that produced the bad finding, including the overloaded services."""
    return SystemPassport(
        id="builtwatch",
        name="BuiltWatch",
        purpose="Watch external sources for changes affecting systems I have built.",
        technologies=["Strands Agents", "AWS SDK", "Cloudflare Workers"],
        # Note these are sources the system *monitors*, not things it depends on.
        services=[
            "CISA Known Exploited Vulnerabilities (KEV)",
            "EU AI Act / Article 50",
            "Amazon Bedrock updates",
        ],
    )


def test_the_original_windows_finding_is_rejected(builtwatch_passport):
    assert affected_product_undeclared(builtwatch_passport, WINDOWS_ADVISORY) is True


@pytest.mark.parametrize(
    "advisory",
    [
        "Critical Linux kernel privilege escalation allows local root.",
        "OpenSSL heap overflow in certificate parsing, CVE-2026-11111.",
        "Apache Log4j remote code execution via JNDI lookup.",
        "Kubernetes API server authentication bypass flaw.",
        "nginx buffer overflow in the HTTP/3 module.",
        "Fortinet FortiOS SSL-VPN path traversal actively exploited.",
    ],
)
def test_products_no_allowlist_anticipated_are_also_rejected(builtwatch_passport, advisory):
    """The previous allowlist caught only Windows. None of these were covered."""
    assert affected_product_undeclared(builtwatch_passport, advisory) is True


def test_a_genuinely_relevant_advisory_survives(builtwatch_passport):
    """The test must not simply suppress everything — a real hit has to get through."""
    advisory = (
        "Cloudflare Workers runtime: a sandbox escape in the V8 isolate allows "
        "cross-tenant code execution. Upgrade immediately."
    )
    assert affected_product_undeclared(builtwatch_passport, advisory) is False


def test_generic_words_alone_never_establish_applicability():
    """'service'/'api'/'cloud' appear in nearly every advisory and prove nothing."""
    passport = SystemPassport(
        id="vague", name="Vague", purpose="p", technologies=["API service"], services=["cloud"]
    )
    assert "api" not in declared_terms(passport)
    assert "cloud" not in declared_terms(passport)
    assert affected_product_undeclared(passport, "A cloud API service vulnerability.") is True


def test_fabricated_usage_claim_is_detected(builtwatch_passport):
    """The exact inference from the bad finding."""
    claims = unsupported_usage_claims(
        builtwatch_passport,
        ["The system uses Microsoft Windows, which now has a known vulnerability."],
    )
    assert claims and "microsoft windows" in claims[0].lower()


@pytest.mark.parametrize(
    "statement",
    [
        "The system runs on Ubuntu Linux servers.",
        "The application relies on Log4j for logging.",
        "It is built on Kubernetes.",
        "The app depends on OpenSSL for TLS termination.",
    ],
)
def test_undeclared_dependency_assertions_are_detected(builtwatch_passport, statement):
    assert unsupported_usage_claims(builtwatch_passport, [statement])


def test_declared_dependency_assertions_are_allowed(builtwatch_passport):
    """A true statement about the declared stack must not be flagged."""
    assert (
        unsupported_usage_claims(
            builtwatch_passport, ["The system uses Cloudflare Workers to serve the frontend."]
        )
        == []
    )


def test_vague_claims_are_not_treated_as_fabrication(builtwatch_passport):
    """Naming nothing specific is imprecision, not invention. Don't punish it here."""
    assert unsupported_usage_claims(builtwatch_passport, ["The system uses a service."]) == []


def test_quality_version_is_positive():
    """Bumped whenever assessment rules change; drives cache invalidation and retraction."""
    assert QUALITY_VERSION >= 4
