from datetime import date

from app.agent.resolve import resolve_transaction
from app.agent.schemas import ParseOutput
from app.routers.chat import AgentContext


def build_context(*, accounts=None, expense_categories=None, income_categories=None, last_used=None):
    accounts = accounts or ["Efectivo", "Galicia", "Naranja X"]
    expense_categories = expense_categories or [
        {"name": "Alimentación", "code": "e1", "subcategories": [{"name": "Delivery", "code": "e1.1"}]},
    ]
    income_categories = income_categories or [
        {"name": "Salario", "code": "i1", "subcategories": [{"name": "Sueldo", "code": "i1.1"}]},
    ]
    return AgentContext(
        account_codes={"Efectivo": "a1", "Galicia": "a2", "Naranja X": "a3"},
        account_id_to_name={"a1": "Efectivo", "a2": "Galicia", "a3": "Naranja X"},
        account_id_to_currency={"a1": "ARS", "a2": "ARS", "a3": "ARS"},
        expense_category_codes={"Alimentación": "e1"},
        expense_subcategory_codes={"e1": {"Delivery": "e1.1"}},
        income_category_codes={"Salario": "i1"},
        income_subcategory_codes={"i1": {"Sueldo": "i1.1"}},
        expense_category_id_to_name={"e1": "Alimentación"},
        expense_subcategory_id_to_name={"e1.1": "Delivery"},
        income_category_id_to_name={"i1": "Salario"},
        income_subcategory_id_to_name={"i1.1": "Sueldo"},
        last_used_account_ids=last_used or {},
    )


def test_resolve_keeps_pending_amount_when_only_account_is_supplied():
    ctx = build_context()
    patch = ParseOutput(kind="transaction", tx_type="expense", account="a3", starts_new_transaction=False)
    pending = {"type": "expense", "amount": 10198.0, "description": "Delivery McDonald's", "currency": "ARS"}

    result = resolve_transaction(patch, pending, ctx, date(2026, 1, 1))

    assert result["response_type"] == "draft"
    assert result["payload"]["amount"] == 10198.0
    assert result["payload"]["account_id"] == "a3"
    assert result["payload"]["description"] == "Delivery McDonald's"


def test_resolve_parses_amount_from_patch_when_pending_missing_amount():
    ctx = build_context()
    patch = ParseOutput(kind="transaction", tx_type="expense", amount_text="20 lucas", starts_new_transaction=False)
    pending = {"type": "expense", "description": "Compu", "currency": "ARS"}

    result = resolve_transaction(patch, pending, ctx, date(2026, 1, 1))

    assert result["response_type"] == "clarification"
    assert result["missing_fields"] == ["account"]
    assert result["payload"]["amount"] == 20000.0


def test_resolve_ignores_pending_when_new_transaction_starts():
    ctx = build_context()
    patch = ParseOutput(
        kind="transaction", tx_type="expense", amount_text="15", description="Cena", starts_new_transaction=True
    )
    pending = {"type": "expense", "amount": 30.0, "description": "Viejo", "currency": "ARS"}

    result = resolve_transaction(patch, pending, ctx, date(2026, 1, 1))

    assert result["response_type"] == "clarification"
    assert result["missing_fields"] == ["account"]
    assert result["payload"]["amount"] == 15.0


def test_resolve_infers_last_used_account_when_available():
    ctx = build_context(last_used={("expense", "ARS"): "a2"})
    patch = ParseOutput(
        kind="transaction", tx_type="expense", amount_text="500", description="Cena", starts_new_transaction=False
    )
    pending = {"type": "expense", "description": "Cena", "currency": "ARS"}

    result = resolve_transaction(patch, pending, ctx, date(2026, 1, 1))

    assert result["response_type"] == "draft"
    assert result["payload"]["account_id"] == "a2"
    assert result["inferred_fields"] == ["account"]


def test_resolve_requires_account_when_nothing_to_infer():
    ctx = build_context(last_used={})
    patch = ParseOutput(
        kind="transaction", tx_type="expense", amount_text="500", description="Cena", starts_new_transaction=False
    )
    pending = {"type": "expense", "description": "Cena", "currency": "ARS"}

    result = resolve_transaction(patch, pending, ctx, date(2026, 1, 1))

    assert result["response_type"] == "clarification"
    assert result["missing_fields"] == ["account"]


def test_resolve_drops_income_category_when_expense_type():
    ctx = build_context()
    patch = ParseOutput(
        kind="transaction",
        tx_type="expense",
        account="a1",
        category="i1",
        subcategory="i1.1",
        amount_text="100",
        description="Cena",
        starts_new_transaction=False,
    )
    pending = {"type": "expense", "currency": "ARS"}

    result = resolve_transaction(patch, pending, ctx, date(2026, 1, 1))

    assert result["response_type"] == "draft"
    assert result["payload"].get("category_id") is None


def test_resolve_drops_unknown_ids_from_pending():
    ctx = build_context()
    patch = ParseOutput(
        kind="transaction", tx_type="expense", amount_text="500", description="Cena", starts_new_transaction=False
    )
    pending = {"type": "expense", "account_id": "unknown", "category_id": "bad", "currency": "ARS"}

    result = resolve_transaction(patch, pending, ctx, date(2026, 1, 1))

    assert result["response_type"] == "clarification"
    assert result["payload"].get("account_id") is None


def test_resolve_transfer_same_account_is_disallowed():
    ctx = build_context()
    patch = ParseOutput(
        kind="transaction",
        tx_type="transfer",
        amount_text="50",
        description="Transferencia",
        account="a2",
        account_destination="a2",
        starts_new_transaction=False,
    )
    pending = {"type": "transfer", "currency": "ARS"}

    result = resolve_transaction(patch, pending, ctx, date(2026, 1, 1))

    assert result["response_type"] == "clarification"
    assert result["message"] == "No podés transferir entre la misma cuenta."


def test_resolve_installments_math_and_success_message():
    ctx = build_context()
    patch = ParseOutput(
        kind="transaction",
        tx_type="expense",
        amount_text="1000",
        description="Cafetera",
        account="a1",
        installments=3,
        starts_new_transaction=False,
    )
    pending = {"type": "expense", "currency": "ARS"}

    result = resolve_transaction(patch, pending, ctx, date(2026, 1, 1))

    assert result["response_type"] == "draft"
    assert result["payload"]["installment_amount"] == 333.33
    assert result["message"] == "¡Listo! Revisá los detalles y confirmá si todo está bien."


def test_resolve_marks_amount_missing_when_text_is_unparseable():
    ctx = build_context()
    patch = ParseOutput(
        kind="transaction", tx_type="expense", amount_text="abc", description="Cena", starts_new_transaction=False
    )
    pending = {"type": "expense", "currency": "ARS"}

    result = resolve_transaction(patch, pending, ctx, date(2026, 1, 1))

    assert result["response_type"] == "clarification"
    assert result["missing_fields"] == ["amount"]
