"""Tests for the schema field caps (PR-C.5, R1 high#5).

PR-C.5 caps the ``LoginRequest.password`` field at 256 characters and
the ``QuestionRequest.question`` field at 2048 characters. The
upper bounds protect the downstream KDF (argon2) and the retrieval
pipeline from oversized inputs. The 4R review caught that the prior
fields had no upper bound at all.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dafi_sentinel.api.schemas import LoginRequest, QuestionRequest


def test_login_password_max_length_is_256():
    """A 256-char password is accepted; a 257-char password is rejected."""
    LoginRequest(username="ada", password="a" * 256)
    with pytest.raises(ValidationError):
        LoginRequest(username="ada", password="a" * 257)


def test_login_username_has_upper_bound():
    """A 129-char username is rejected (sanity: matches the 4R floor)."""
    LoginRequest(username="a" * 128, password="hunter2!")
    with pytest.raises(ValidationError):
        LoginRequest(username="a" * 129, password="hunter2!")


def test_question_max_length_is_2048():
    """A 2048-char question is accepted; a 2049-char question is rejected."""
    QuestionRequest(question="q" * 2048, session_id="s")
    with pytest.raises(ValidationError):
        QuestionRequest(question="q" * 2049, session_id="s")


def test_question_session_id_has_upper_bound():
    """Session id is bounded too so a multi-KB id cannot reach the workbench."""
    QuestionRequest(question="q", session_id="s" * 128)
    with pytest.raises(ValidationError):
        QuestionRequest(question="q", session_id="s" * 129)


def test_login_min_length_still_enforced():
    """The pre-PR-C.5 min_length=1 contract is preserved."""
    with pytest.raises(ValidationError):
        LoginRequest(username="", password="hunter2!")
    with pytest.raises(ValidationError):
        LoginRequest(username="ada", password="")


def test_question_min_length_still_enforced():
    """Empty question is still rejected (no behavior change at the low end)."""
    with pytest.raises(ValidationError):
        QuestionRequest(question="", session_id="s")
