from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, Request, status

WINDOW_SECONDS = 15 * 60
MAX_ATTEMPTS = 5
_attempts: dict[str, deque[float]] = defaultdict(deque)


async def enforce_auth_rate_limit(request: Request, email: str, action: str) -> None:
    # Este límite vive por proceso; un despliegue con varios workers necesita un store compartido.
    key = f"{action}:{request.client.host if request.client else 'unknown'}:{email}"
    now = monotonic()
    attempts = _attempts[key]
    while attempts and now - attempts[0] >= WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos. Probá de nuevo más tarde.",
        )
    attempts.append(now)
