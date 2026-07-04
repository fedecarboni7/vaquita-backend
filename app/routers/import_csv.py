import csv
import io
import time
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.account import Account
from app.models.category import Category
from app.models.subcategory import Subcategory
from app.models.transaction import Transaction, TransactionType
from app.models.user import User

router = APIRouter(prefix="/import", tags=["import"])

STAGING_TTL_SECONDS = 1800

REQUIRED_COLUMNS = [
    "date",
    "type",
    "amount",
    "currency",
    "account_name",
    "category_name",
    "subcategory_name",
    "account_destination_name",
    "to_amount",
    "to_currency",
    "description",
]

VALID_TYPES = frozenset({"expense", "income", "transfer"})


@dataclass
class StagingData:
    created_at: float
    rows: list[dict[str, Any]]
    account_currencies: dict[str, str]


_staging_store: dict[str, StagingData] = {}


def _clean_expired_staging() -> None:
    now = time.time()
    expired = [k for k, v in _staging_store.items() if now - v.created_at > STAGING_TTL_SECONDS]
    for k in expired:
        del _staging_store[k]


def _get_staging_data(token: str) -> StagingData:
    _clean_expired_staging()
    data = _staging_store.get(token)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de staging inválido o expirado",
        )
    return data


class UniquePairOut(BaseModel):
    category_name: str | None = None
    subcategory_name: str | None = None


class PreviewImportOut(BaseModel):
    staging_token: str
    transaction_count: int
    unique_pairs: list[UniquePairOut]


class CategoryMappingIn(BaseModel):
    category_name: str | None = None
    subcategory_name: str | None = None
    existing_category_id: uuid.UUID | None = None
    existing_subcategory_id: uuid.UUID | None = None


class ConfirmImportIn(BaseModel):
    staging_token: str
    mapping: list[CategoryMappingIn]


class ConfirmImportOut(BaseModel):
    created_transactions: int
    created_accounts: list[str]
    created_categories: list[str]
    created_subcategories: list[str]


def _validate_csv_headers(fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo CSV está vacío o no tiene encabezados",
        )

    normalized = [h.strip() for h in fieldnames]
    if len(normalized) != len(REQUIRED_COLUMNS) or any(a != b for a, b in zip(normalized, REQUIRED_COLUMNS)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El archivo CSV debe tener exactamente {len(REQUIRED_COLUMNS)} columnas: {', '.join(REQUIRED_COLUMNS)}"
            ),
        )


def _parse_date(raw: str, row_number: int) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fila {row_number}: fecha '{raw}' no válida",
        )


def _parse_type(raw: str, row_number: int) -> str:
    val = raw.strip().lower()
    if val not in VALID_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Fila {row_number}: tipo de transacción '{raw}' no válido. "
                "Los valores permitidos son: expense, income, transfer."
            ),
        )
    return val


def _parse_amount(raw: str, row_number: int, field: str) -> Decimal:
    val = raw.strip()
    if not val:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fila {row_number}: {field} requerido",
        )
    try:
        amount = Decimal(val)
        if amount <= 0:
            raise ValueError
        return amount
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fila {row_number}: {field} '{raw}' no válido",
        )


def _parse_and_validate_rows(content: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(content))
    _validate_csv_headers(reader.fieldnames)

    rows: list[dict[str, Any]] = []
    account_currency_sets: dict[str, set[str]] = {}

    for row_index, csv_row in enumerate(reader, start=1):
        row = {k.strip() if k else k: (v.strip() if v else "") for k, v in csv_row.items()}

        parsed: dict[str, Any] = {}
        parsed["date"] = _parse_date(row.get("date", ""), row_index)
        parsed["type"] = _parse_type(row.get("type", ""), row_index)
        parsed["amount"] = _parse_amount(row.get("amount", ""), row_index, "monto")
        parsed["currency"] = row.get("currency", "").upper()
        if not parsed["currency"] or len(parsed["currency"]) != 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Fila {row_index}: moneda '{row.get('currency', '')}' no válida",
            )

        account_name = row.get("account_name", "")
        if not account_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Fila {row_index}: nombre de cuenta origen requerido",
            )
        parsed["account_name"] = account_name

        cat = row.get("category_name", "")
        parsed["category_name"] = cat if cat else None
        sub = row.get("subcategory_name", "")
        parsed["subcategory_name"] = sub if sub else None
        parsed["description"] = row.get("description", "") or None

        dest = row.get("account_destination_name", "")
        parsed["account_destination_name"] = dest if dest else None

        to_amount_raw = row.get("to_amount", "")
        parsed["to_amount"] = _parse_amount(to_amount_raw, row_index, "monto destino") if to_amount_raw else None
        to_cur = row.get("to_currency", "")
        parsed["to_currency"] = to_cur if to_cur else None

        # Validation: transfer rows must have account_destination_name
        if parsed["type"] == "transfer" and parsed["account_destination_name"] is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Fila {row_index}: las transferencias requieren una cuenta destino",
            )

        src_currency = parsed["currency"]
        account_currency_sets.setdefault(account_name, set()).add(src_currency)

        if parsed["account_destination_name"]:
            dest_currency = parsed["to_currency"] or src_currency
            account_currency_sets.setdefault(parsed["account_destination_name"], set()).add(dest_currency)

        rows.append(parsed)

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo CSV no contiene filas de datos",
        )

    # Validate transfer destination appears as a source account (has transactions)
    source_account_names = {r["account_name"] for r in rows}
    for row in rows:
        if row["type"] == "transfer":
            dest_name = row["account_destination_name"]
            if dest_name not in source_account_names:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(f"Fila {rows.index(row) + 1}: la cuenta destino '{dest_name}' no existe en el archivo"),
                )

    # Validate no mixed currencies per account
    for account_name, currencies in account_currency_sets.items():
        if len(currencies) > 1:
            sorted_currencies = ", ".join(sorted(currencies))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(f"La cuenta '{account_name}' tiene monedas mixtas: {sorted_currencies}"),
            )

    return rows


def _build_account_currencies(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Build validated account_name -> currency map from parsed rows."""
    currency_sets: dict[str, set[str]] = {}
    for row in rows:
        src = row["account_name"]
        currency_sets.setdefault(src, set()).add(row["currency"])
        dest = row.get("account_destination_name")
        if dest:
            dest_currency = row.get("to_currency") or row["currency"]
            currency_sets.setdefault(dest, set()).add(dest_currency)
    return {name: next(iter(currencies)) for name, currencies in currency_sets.items()}


def _build_unique_pairs(rows: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    seen: set[tuple[str, str | None]] = set()
    pairs: list[dict[str, str | None]] = []
    for row in rows:
        cat = row["category_name"]
        if cat is None:
            continue
        sub = row["subcategory_name"]
        key = (cat, sub)
        if key not in seen:
            seen.add(key)
            pairs.append({"category_name": cat, "subcategory_name": sub})
    return pairs


@router.post("/preview", response_model=PreviewImportOut)
async def preview_import(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PreviewImportOut:
    del session

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe tener extensión .csv",
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo CSV está vacío",
        )

    try:
        content = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo CSV debe estar codificado en UTF-8",
        )

    rows = _parse_and_validate_rows(content)
    account_currencies = _build_account_currencies(rows)
    pairs = _build_unique_pairs(rows)

    token = str(uuid.uuid4())
    _staging_store[token] = StagingData(
        created_at=time.time(),
        rows=rows,
        account_currencies=account_currencies,
    )

    return PreviewImportOut(
        staging_token=token,
        transaction_count=len(rows),
        unique_pairs=[UniquePairOut(**p) for p in pairs],
    )


@router.post("/confirm", response_model=ConfirmImportOut, status_code=status.HTTP_201_CREATED)
async def confirm_import(
    body: ConfirmImportIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConfirmImportOut:
    staging = _get_staging_data(body.staging_token)

    # Phase 1: create new categories (deduplicated by name)
    cat_name_to_new_id: dict[str, uuid.UUID] = {}
    created_category_names: list[str] = []
    for m in body.mapping:
        if m.existing_category_id is None and m.category_name and m.category_name not in cat_name_to_new_id:
            cat = Category(
                id=uuid.uuid4(),
                user_id=current_user.id,
                name=m.category_name,
                type="expense",
            )
            session.add(cat)
            cat_name_to_new_id[m.category_name] = cat.id
            created_category_names.append(m.category_name)

    # Phase 2: resolve all mappings
    pair_resolution: dict[tuple[str | None, str | None], tuple[uuid.UUID | None, uuid.UUID | None]] = {}
    created_subcategory_names: list[str] = []
    for m in body.mapping:
        key = (m.category_name, m.subcategory_name)

        if m.existing_category_id is not None:
            cat = await session.get(Category, m.existing_category_id)
            if cat is None or cat.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Categoría '{m.existing_category_id}' no encontrada",
                )
            resolved_category_id = cat.id
        elif m.category_name:
            resolved_category_id = cat_name_to_new_id[m.category_name]
        else:
            resolved_category_id = None

        if m.subcategory_name is not None:
            if m.existing_subcategory_id is not None:
                sub = await session.get(Subcategory, m.existing_subcategory_id)
                if sub is None or sub.user_id != current_user.id or sub.category_id != resolved_category_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Subcategoría no encontrada o no pertenece a la categoría",
                    )
                resolved_subcategory_id = sub.id
            else:
                sub = Subcategory(
                    id=uuid.uuid4(),
                    name=m.subcategory_name,
                    category_id=resolved_category_id,
                    user_id=current_user.id,
                )
                session.add(sub)
                resolved_subcategory_id = sub.id
                created_subcategory_names.append(m.subcategory_name)
        else:
            resolved_subcategory_id = None

        pair_resolution[key] = (resolved_category_id, resolved_subcategory_id)

    # Create accounts (always new, never match existing)
    account_name_to_id: dict[str, uuid.UUID] = {}
    created_account_names: list[str] = []
    for name, currency in staging.account_currencies.items():
        account = Account(
            id=uuid.uuid4(),
            user_id=current_user.id,
            name=name,
            account_type="savings",
            currency=currency,
            include_in_total=True,
        )
        session.add(account)
        account_name_to_id[name] = account.id
        created_account_names.append(name)

    # Create transactions
    created_count = 0
    for row in staging.rows:
        source_account_id = account_name_to_id[row["account_name"]]

        destination_account_id = None
        if row["account_destination_name"]:
            destination_account_id = account_name_to_id[row["account_destination_name"]]

        cat_key = (row["category_name"], row["subcategory_name"])
        cat_id, subcat_id = pair_resolution.get(cat_key, (None, None))

        transaction = Transaction(
            id=uuid.uuid4(),
            user_id=current_user.id,
            amount=row["amount"],
            currency=row["currency"],
            type=TransactionType(row["type"]),
            account_id=source_account_id,
            category_id=cat_id,
            subcategory_id=subcat_id,
            description=row["description"],
            note=None,
            installments=None,
            account_destination_id=destination_account_id,
            to_amount=row["to_amount"],
            affects_balance=True,
            expense_date=row["date"],
            chat_thread_id=None,
        )
        session.add(transaction)
        created_count += 1

    await session.commit()

    # Invalidate staging token
    _staging_store.pop(body.staging_token, None)

    return ConfirmImportOut(
        created_transactions=created_count,
        created_accounts=created_account_names,
        created_categories=created_category_names,
        created_subcategories=created_subcategory_names,
    )
