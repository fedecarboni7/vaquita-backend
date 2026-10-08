import pytest

from app.agent.nodes import _invoke_with_retry


class _StubStructuredLlm:
    def __init__(self, effects):
        self._effects = list(effects)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        effect = self._effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


def test_retry_succeeds_after_one_failure():
    stub = _StubStructuredLlm([ValueError("bad output"), "ok"])

    assert _invoke_with_retry(stub, ["msg"]) == "ok"
    assert stub.calls == 2


def test_retry_raises_after_two_failures():
    stub = _StubStructuredLlm([ValueError("first"), TypeError("second")])

    with pytest.raises((ValueError, TypeError)):
        _invoke_with_retry(stub, ["msg"])
    assert stub.calls == 2


def test_no_retry_when_first_attempt_succeeds():
    stub = _StubStructuredLlm(["ok"])

    assert _invoke_with_retry(stub, ["msg"]) == "ok"
    assert stub.calls == 1


def test_non_retryable_error_propagates_immediately():
    stub = _StubStructuredLlm([RuntimeError("boom"), "ok"])

    with pytest.raises(RuntimeError):
        _invoke_with_retry(stub, ["msg"])
    assert stub.calls == 1
