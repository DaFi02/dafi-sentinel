"""Parametrized redaction tests for the security policy (R1 med#11, R3 F10).

The 4R review caught that the redaction regex
(``dafi_sentinel.security.policy.SECRET_PATTERN``) only covered a
narrow set of credential shapes (``sk_live_...`` / ``sk_test_...``
and ``password=...``). Several common secret shapes that show up
in incident text are NOT redacted:

* ``aws_access_key_id=AKIA...`` (AWS access key)
* ``github_pat_11ABCDEFG...`` (GitHub personal access token)
* ``eyJ...`` JSON Web Tokens
* ``api_key=...`` generic API key

The regex expansion lands in PR-C.13. This module pins the
contract the expansion MUST satisfy; each new pattern is marked
``xfail`` so the test runs and reports the gap instead of silently
passing. When PR-C.13 lands, the ``xfail`` markers flip to
``xpass`` and the regex is verified against the new surface.
"""

from __future__ import annotations

import pytest

from dafi_sentinel.security.policy import RedactionService


@pytest.fixture
def redactor() -> RedactionService:
    return RedactionService()


@pytest.mark.parametrize(
    "raw, expected_marker",
    [
        # AWS access keys: the canonical ``AKIA`` prefix and the
        # newer ``ASIA`` (STS) prefix are both accepted.
        ("aws_access_key_id=AKIAIOSFODNN7EXAMPLE", "[REDACTED:SECRET:"),
        ("aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "[REDACTED:SECRET:"),
        # GitHub personal access tokens (the ``github_pat_`` prefix
        # introduced in 2022; classic ``ghp_`` tokens are also
        # common in incident dumps).
        ("token=github_pat_11ABCDEFG_abcdefghij1234567890", "[REDACTED:SECRET:"),
        # JSON Web Tokens: three dot-separated base64url segments.
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1LTEifQ.signature", "[REDACTED:SECRET:"),
        # Generic API key: the dashboard imports data from sources
        # that carry their own ``api_key=`` field.
        ("config.api_key=sk-1234567890abcdef", "[REDACTED:SECRET:"),
    ],
)
@pytest.mark.xfail(
    reason=(
        "R1 med#11 / R3 F10: SECRET_PATTERN expansion lands in PR-C.13. "
        "The xfail markers flip to xpass when the regex is widened to "
        "cover aws_*, github_pat_*, JWT, and api_key= shapes."
    ),
    strict=False,
)
def test_redaction_covers_additional_secret_shapes(redactor: RedactionService, raw: str, expected_marker: str) -> None:
    """Every common secret shape must be redacted in a single pass.

    The parametrized cases cover the four shapes the 4R review
    flagged. The xfail marker documents the gap; when PR-C.13
    expands the regex, the same cases turn green and the test
    suite proves the expansion matches the contract.
    """
    redacted = redactor.redact_text(raw)
    assert expected_marker in redacted, (
        f"redactor must mark {raw!r} as a SECRET; got {redacted!r}"
    )
    # And the original secret MUST NOT survive the redaction.
    assert raw not in redacted, (
        f"redactor must not leak the raw secret; got {redacted!r}"
    )


def test_existing_stripe_and_password_shapes_still_redact(redactor: RedactionService) -> None:
    """Regression: the original ``sk_live_`` / ``password=`` shapes still redact.

    Pins the prior behavior so a future regex expansion in
    PR-C.13 does not silently drop the existing surface.
    """
    redacted = redactor.redact_text(
        "token=sk_live_123456 password=hunter2",
    )
    assert "[REDACTED:SECRET:" in redacted
    assert "sk_live_123456" not in redacted
    assert "hunter2" not in redacted
