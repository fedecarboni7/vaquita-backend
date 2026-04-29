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
        "account_name_to_id": {"banco": "11111111-1111-1111-1111-111111111111"},
    }

    result = validate(state)
    payload = result["response_payload"]

    assert payload["installment_amount"] == 333.33
    assert payload["account_id"] == "11111111-1111-1111-1111-111111111111"


def test_add_months_clamps_to_last_day_when_needed() -> None:
    assert _add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert _add_months(date(2026, 1, 31), 2) == date(2026, 3, 31)


def test_validate_formats_message_amount_with_argentina_separators() -> None:
    state = {
        "extractor_output": {
            "amount": 1234567.89,
            "description": "Venta freelance",
            "account": "Banco",
        },
        "classifier_output": ClassifierOutput(intent="register", subtype="income"),
        "accounts": ["Banco"],
        "account_name_to_id": {"banco": "11111111-1111-1111-1111-111111111111"},
    }

    result = validate(state)
    assistant_message = result["messages"][0].content

    assert assistant_message == "¡Listo! Revisá los detalles y confirmá si todo está bien."


def test_validate_returns_clarification_when_account_is_invalid() -> None:
    state = {
        "extractor_output": {
            "amount": 2500.0,
            "description": "Cena",
            "account": "Cuenta Fantasma",
        },
        "classifier_output": ClassifierOutput(intent="register", subtype="expense"),
        "accounts": ["Banco", "Efectivo"],
        "account_name_to_id": {
            "banco": "11111111-1111-1111-1111-111111111111",
            "efectivo": "22222222-2222-2222-2222-222222222222",
        },
    }

    result = validate(state)

    assert result["response_type"] == "clarification"
    assert result["response_payload"] is None
    assert "Cuenta Fantasma" in result["messages"][0].content


def test_validate_transfer_preserves_to_amount_in_draft_payload() -> None:
    state = {
        "extractor_output": {
            "amount": 100.0,
            "to_amount": 120000.0,
            "description": "Transferencia USD a ARS",
            "account": "Caja USD",
            "account_destination": "Caja ARS",
            "currency": "USD",
        },
        "classifier_output": ClassifierOutput(intent="register", subtype="transfer"),
        "accounts": ["Caja USD", "Caja ARS"],
        "account_name_to_id": {
            "caja usd": "11111111-1111-1111-1111-111111111111",
            "caja ars": "22222222-2222-2222-2222-222222222222",
        },
    }

    result = validate(state)
    payload = result["response_payload"]

    assert payload["to_amount"] == 120000.0
    assert payload["account_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["account_destination_id"] == "22222222-2222-2222-2222-222222222222"
