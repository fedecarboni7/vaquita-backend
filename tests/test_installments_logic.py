from datetime import date

from app.agent.nodes import validate
from app.agent.schemas import ClassifierOutput
from app.routers.expenses import _add_months


def test_validate_adds_installment_amount_when_installments_present() -> None:
    state = {
        "extractor_output": {
            "amount": 1000.0,
            "description": "Notebook",
            "account": "Banco",
            "installments": 3,
        },
        "classifier_output": ClassifierOutput(intent="register", subtype="expense"),
        "accounts": ["Banco"],
    }

    result = validate(state)
    payload = result["response_payload"]

    assert payload["installment_amount"] == 333.33


def test_add_months_clamps_to_last_day_when_needed() -> None:
    assert _add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert _add_months(date(2026, 1, 31), 2) == date(2026, 3, 31)
