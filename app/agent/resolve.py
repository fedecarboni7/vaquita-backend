from __future__ import annotations

from datetime import date
from math import floor
from typing import Any

from app.agent.amounts import parse_amount_text
from app.agent.schemas import ParseOutput


def _safe_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def _build_account_name(ctx: Any, account_id: str | None) -> str | None:
    if not account_id:
        return None
    account_id_to_name = getattr(ctx, "account_id_to_name", {})
    return account_id_to_name.get(account_id)


def _build_category_info(ctx: Any, tx_type: str, category_value: str | None):
    if not category_value:
        return None, None, None, None

    category_id_to_name = (
        getattr(ctx, "expense_category_id_to_name", {})
        if tx_type == "expense"
        else getattr(ctx, "income_category_id_to_name", {})
    )
    category_codes = (
        getattr(ctx, "expense_category_codes", {})
        if tx_type == "expense"
        else getattr(ctx, "income_category_codes", {})
    )
    category_code_to_id = (
        getattr(ctx, "expense_category_code_to_id", {})
        if tx_type == "expense"
        else getattr(ctx, "income_category_code_to_id", {})
    )

    if category_value in category_code_to_id:
        category_id = category_code_to_id[category_value]
        category_name = category_id_to_name.get(category_id) or category_value
        return category_id, category_name, category_name, category_id

    for name, code in category_codes.items():
        if code == category_value or name.lower() == category_value.lower():
            category_id = category_code_to_id.get(code, code)
            category_name = category_id_to_name.get(category_id, name)
            return category_id, category_name, category_name, category_id

    return None, None, None, None


def _build_subcategory_info(ctx: Any, tx_type: str, category_id: str | None, subcategory_value: str | None):
    if not category_id or not subcategory_value:
        return None, None, None, None

    subcategory_map = (
        getattr(ctx, "expense_subcategory_codes", {})
        if tx_type == "expense"
        else getattr(ctx, "income_subcategory_codes", {})
    )
    subcategory_code_to_id = (
        getattr(ctx, "expense_subcategory_code_to_id", {})
        if tx_type == "expense"
        else getattr(ctx, "income_subcategory_code_to_id", {})
    )
    subcategory_id_to_name = (
        getattr(ctx, "expense_subcategory_id_to_name", {})
        if tx_type == "expense"
        else getattr(ctx, "income_subcategory_id_to_name", {})
    )

    for category_code, items in subcategory_map.items():
        for name, code in items.items():
            if code == subcategory_value or name.lower() == subcategory_value.lower():
                subcategory_id = subcategory_code_to_id.get(category_code, {}).get(code, code)
                subcategory_name = subcategory_id_to_name.get(subcategory_id, name)
                return category_code, subcategory_id, subcategory_name, category_code
        if category_code == category_id or category_code == str(category_id):
            return category_code, None, None, category_code

    return None, None, None, None


def _resolve_account(ctx: Any, account_value: str | None):
    if not account_value:
        return None, None

    account_id_to_name = getattr(ctx, "account_id_to_name", {})
    if account_value in account_id_to_name:
        return account_value, account_id_to_name[account_value]

    account_codes = getattr(ctx, "account_codes", {})
    for name, code in account_codes.items():
        if code == account_value or name.lower() == account_value.lower():
            account_code_to_id = getattr(ctx, "account_code_to_id", {})
            account_id = account_code_to_id.get(code, code)
            return account_id, account_id_to_name.get(account_id, name)

    return None, None


def _resolve_category(ctx: Any, tx_type: str, category_value: str | None):
    if not category_value:
        return None, None
    return _build_category_info(ctx, tx_type, category_value)[:2]


def _sanitize_pending(pending: dict[str, Any] | None, ctx: Any) -> dict[str, Any]:
    if not pending:
        return {}

    sanitized: dict[str, Any] = {}
    tx_type = pending.get("type")
    if tx_type in {"expense", "income", "transfer"}:
        sanitized["type"] = tx_type

    for field in ["amount", "to_amount", "description", "expense_date", "currency", "installments", "note"]:
        if field in pending:
            sanitized[field] = pending[field]

    account_id = pending.get("account_id")
    if account_id and account_id in getattr(ctx, "account_id_to_name", {}):
        sanitized["account_id"] = account_id

    account_destination_id = pending.get("account_destination_id")
    if account_destination_id and account_destination_id in getattr(ctx, "account_id_to_name", {}):
        sanitized["account_destination_id"] = account_destination_id

    category_id = pending.get("category_id")
    if category_id:
        valid_expense = category_id in getattr(ctx, "expense_category_id_to_name", {})
        valid_income = category_id in getattr(ctx, "income_category_id_to_name", {})
        if (tx_type == "expense" and valid_expense) or (tx_type == "income" and valid_income):
            sanitized["category_id"] = category_id

    subcategory_id = pending.get("subcategory_id")
    if subcategory_id:
        valid_expense = subcategory_id in getattr(ctx, "expense_subcategory_id_to_name", {})
        valid_income = subcategory_id in getattr(ctx, "income_subcategory_id_to_name", {})
        if (tx_type == "expense" and valid_expense) or (tx_type == "income" and valid_income):
            sanitized["subcategory_id"] = subcategory_id

    if sanitized.get("type") == "transfer":
        sanitized.pop("category_id", None)
        sanitized.pop("subcategory_id", None)
        sanitized.pop("installments", None)

    if sanitized.get("type") in {"expense", "income"} and sanitized.get("installments") is not None:
        installments = int(sanitized["installments"])
        if installments < 1 or installments > 60:
            sanitized.pop("installments", None)

    return sanitized


def _hydrate_pending_to_payload(base: dict[str, Any], ctx: Any, tx_type: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": tx_type}
    if base.get("amount") is not None:
        payload["amount"] = float(base["amount"])
    if base.get("to_amount") is not None:
        payload["to_amount"] = float(base["to_amount"])
    if base.get("description"):
        payload["description"] = base["description"]
    if base.get("currency"):
        payload["currency"] = base["currency"]
    if base.get("installments") is not None:
        payload["installments"] = int(base["installments"])
    if base.get("note"):
        payload["note"] = base["note"]
    if base.get("expense_date"):
        payload["expense_date"] = base["expense_date"]

    account_id = base.get("account_id")
    if account_id:
        payload["account_id"] = account_id
        payload["account"] = _build_account_name(ctx, account_id)

    destination_id = base.get("account_destination_id")
    if destination_id:
        payload["account_destination_id"] = destination_id
        payload["account_destination"] = _build_account_name(ctx, destination_id)

    category_id = base.get("category_id")
    if category_id:
        category_name = None
        if tx_type == "expense":
            category_name = getattr(ctx, "expense_category_id_to_name", {}).get(category_id)
        elif tx_type == "income":
            category_name = getattr(ctx, "income_category_id_to_name", {}).get(category_id)
        if category_name:
            payload["category_id"] = category_id
            payload["category"] = category_name
            payload["category_name"] = category_name

    subcategory_id = base.get("subcategory_id")
    if subcategory_id:
        subcategory_name = None
        if tx_type == "expense":
            subcategory_name = getattr(ctx, "expense_subcategory_id_to_name", {}).get(subcategory_id)
        elif tx_type == "income":
            subcategory_name = getattr(ctx, "income_subcategory_id_to_name", {}).get(subcategory_id)
        if subcategory_name:
            payload["subcategory_id"] = subcategory_id
            payload["subcategory_name"] = subcategory_name
            payload["subcategory"] = subcategory_name
            payload["category"] = payload.get("category") or payload.get("category_name")

    return payload


def _build_clarification_message(
    tx_type: str, missing_fields: list[str], amount: float | None, account_names: list[str]
) -> str:
    account_text = f" Tenés: {', '.join(account_names)}." if account_names else ""

    if missing_fields == ["amount"]:
        return "¿Cuánto fue?"

    if tx_type == "transfer":
        if "account" in missing_fields:
            return f"¿De qué cuenta salió la plata?{account_text}"
        if "account_destination" in missing_fields:
            return f"¿A qué cuenta fue?{account_text}"
        return "Necesito que aclares la transferencia."

    if amount is not None and "account" in missing_fields:
        if tx_type == "expense":
            return f"¿Con qué cuenta pagaste los ${amount:,.0f}?{account_text}"
        return f"¿En qué cuenta lo recibiste los ${amount:,.0f}?{account_text}"

    if "account" in missing_fields:
        if tx_type == "expense":
            return f"¿Con qué cuenta pagaste?{account_text}"
        return f"¿En qué cuenta lo recibiste?{account_text}"

    return "Necesito que aclares la transacción."


def resolve_transaction(patch: ParseOutput, pending: dict[str, Any] | None, ctx: Any, today: date) -> dict[str, Any]:
    base = {}
    if not (patch.starts_new_transaction or pending is None):
        base = _sanitize_pending(pending, ctx)

    tx_type = patch.tx_type or base.get("type")
    if tx_type is None:
        return {
            "response_type": "clarification",
            "payload": None,
            "message": "¿Fue un gasto, un ingreso o una transferencia?",
            "missing_fields": ["type"],
            "inferred_fields": [],
        }

    payload = _hydrate_pending_to_payload(base, ctx, tx_type)
    inferred_fields: list[str] = []
    missing_fields: list[str] = []
    account_names = list(getattr(ctx, "account_id_to_name", {}).values())

    if patch.amount_text is not None:
        parsed_amount = parse_amount_text(patch.amount_text)
        if parsed_amount is not None:
            payload["amount"] = parsed_amount
        elif "amount" not in payload:
            missing_fields.append("amount")
    elif "amount" not in payload:
        missing_fields.append("amount")

    if patch.to_amount_text is not None:
        parsed_to_amount = parse_amount_text(patch.to_amount_text)
        if parsed_to_amount is not None:
            payload["to_amount"] = parsed_to_amount
        elif "to_amount" not in payload:
            payload["to_amount"] = None

    if patch.description is not None:
        payload["description"] = patch.description
    elif not payload.get("description"):
        if tx_type == "expense":
            payload["description"] = "Gasto"
        elif tx_type == "income":
            payload["description"] = "Ingreso"
        else:
            payload["description"] = "Transferencia"

    if patch.currency is not None:
        payload["currency"] = patch.currency

    if patch.date is not None:
        parsed_date = _safe_date(patch.date)
        if parsed_date:
            payload["expense_date"] = parsed_date

    if patch.account is not None:
        account_id, account_name = _resolve_account(ctx, patch.account)
        if account_id is not None:
            payload["account_id"] = account_id
            payload["account"] = account_name

    if patch.account_destination is not None:
        destination_id, destination_name = _resolve_account(ctx, patch.account_destination)
        if destination_id is not None:
            payload["account_destination_id"] = destination_id
            payload["account_destination"] = destination_name

    if patch.category is not None and tx_type in {"expense", "income"}:
        category_id, category_name = _resolve_category(ctx, tx_type, patch.category)
        if category_id is not None:
            payload["category_id"] = category_id
            payload["category"] = category_name
            payload["category_name"] = category_name

    if patch.subcategory is not None and tx_type in {"expense", "income"}:
        category_id = payload.get("category_id")
        if category_id is None and patch.category is not None:
            category_id, _ = _resolve_category(ctx, tx_type, patch.category)
        category_code, subcategory_id, subcategory_name, _ = _build_subcategory_info(
            ctx, tx_type, category_id, patch.subcategory
        )
        if subcategory_id is not None:
            payload["subcategory_id"] = subcategory_id
            payload["subcategory_name"] = subcategory_name
            payload["subcategory"] = subcategory_name
            if category_id is None and category_code:
                payload["category_id"] = category_code
                payload["category"] = getattr(ctx, f"{tx_type}_category_id_to_name", {}).get(
                    category_code
                ) or payload.get("category")

    if patch.installments is not None and tx_type in {"expense", "income"}:
        try:
            installments = int(patch.installments)
            if installments >= 1:
                payload["installments"] = installments
        except (TypeError, ValueError):
            payload.pop("installments", None)

    if tx_type == "transfer":
        payload.pop("category_id", None)
        payload.pop("category", None)
        payload.pop("category_name", None)
        payload.pop("subcategory_id", None)
        payload.pop("subcategory_name", None)
        payload.pop("subcategory", None)
        payload.pop("installments", None)
        if patch.installments is not None:
            payload.pop("installments", None)

    if tx_type in {"expense", "income"} and payload.get("account_id") is None:
        currency = payload.get("currency") or "ARS"
        last_used = getattr(ctx, "last_used_account_ids", {})
        account_candidate = last_used.get((tx_type, currency))
        if account_candidate:
            account_currencies = getattr(ctx, "account_id_to_currency", {})
            if account_candidate in account_currencies:
                account_currency = account_currencies[account_candidate] or "ARS"
                if account_currency == currency:
                    payload["account_id"] = account_candidate
                    payload["account"] = _build_account_name(ctx, account_candidate)
                    inferred_fields.append("account")

    if (
        tx_type == "transfer"
        and payload.get("account_id")
        and payload.get("account_destination_id") == payload.get("account_id")
    ):
        payload["account_destination_id"] = None
        payload["account_destination"] = None
        return {
            "response_type": "clarification",
            "payload": payload,
            "message": "No podés transferir entre la misma cuenta.",
            "missing_fields": ["account_destination"],
            "inferred_fields": [],
        }

    if tx_type == "transfer":
        if payload.get("account_id") is None and "amount" not in missing_fields:
            missing_fields.append("account")
        if (
            payload.get("account_destination_id") is None
            and payload.get("account_destination") is None
            and "amount" not in missing_fields
        ):
            missing_fields.append("account_destination")
    elif tx_type in {"expense", "income"}:
        if payload.get("account_id") is None and "amount" not in missing_fields:
            missing_fields.append("account")

    if "amount" not in payload or payload.get("amount") is None:
        missing_fields = [field for field in missing_fields if field != "amount"]
        missing_fields.insert(0, "amount")

    if tx_type in {"expense", "income"} and not getattr(ctx, "account_id_to_name", {}):
        return {
            "response_type": "clarification",
            "payload": {"type": tx_type, "description": payload.get("description"), "amount": payload.get("amount")},
            "message": "Primero creá una cuenta para poder registrar la transacción.",
            "missing_fields": ["account"],
            "inferred_fields": [],
        }

    if missing_fields:
        if (
            tx_type == "transfer"
            and payload.get("account_id") is None
            and payload.get("account_destination_id") is None
        ):
            pass
        if tx_type in {"expense", "income"} and payload.get("account_id") is None:
            amount_value = payload.get("amount")
            message = _build_clarification_message(
                tx_type, missing_fields, amount_value if amount_value is not None else None, sorted(account_names)
            )
        else:
            message = _build_clarification_message(
                tx_type, missing_fields, payload.get("amount"), sorted(account_names)
            )
        return {
            "response_type": "clarification",
            "payload": payload,
            "message": message,
            "missing_fields": missing_fields,
            "inferred_fields": [],
        }

    if tx_type in {"expense", "income"}:
        currency = payload.get("currency") or "ARS"
        payload["currency"] = currency
    else:
        payload["currency"] = payload.get("currency") or "ARS"

    if tx_type == "expense" and payload.get("installments") is not None:
        installments = int(payload["installments"])
        if installments >= 1:
            payload["installment_amount"] = floor((float(payload["amount"]) / installments) * 100) / 100
    elif tx_type == "expense" and "installments" in payload:
        payload.pop("installments", None)

    if tx_type == "transfer":
        payload["account_destination"] = payload.get("account_destination")

    message = "¡Listo! Revisá los detalles y confirmá si todo está bien."
    payload["inferred_fields"] = inferred_fields
    return {
        "response_type": "draft",
        "payload": payload,
        "message": message,
        "missing_fields": [],
        "inferred_fields": inferred_fields,
    }
