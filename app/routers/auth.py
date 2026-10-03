from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, get_current_user, verify_google_token
from app.config import settings
from app.database import get_session
from app.models.user import User
from app.schemas.auth import (
    DevAuthRequest,
    EmailRequest,
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SetPasswordRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.services.auth_tokens import (
    EMAIL_VERIFICATION_PURPOSE,
    PASSWORD_RESET_PURPOSE,
    consume_token,
    issue_token,
)
from app.services.email import EmailSender, get_email_sender, send_email_safely
from app.services.email_templates import EmailContent, password_reset_email, verification_email
from app.services.passwords import hash_password, verify_dummy_password, verify_password
from app.services.rate_limit import enforce_auth_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])
GENERIC_AUTH_MESSAGE = "Si el mail es válido, te enviamos un link para verificarlo"
PASSWORD_RESET_MESSAGE = "Si el mail es válido, te enviamos un link para restablecer la contraseña"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def schedule_email(
    background_tasks: BackgroundTasks,
    sender: EmailSender,
    recipient: str,
    content: EmailContent,
) -> None:
    background_tasks.add_task(
        send_email_safely,
        sender,
        recipient,
        content.subject,
        content.html,
        content.text,
    )


@router.post("/google", response_model=TokenResponse)
async def google_auth(
    body: GoogleAuthRequest,
    session: AsyncSession = Depends(get_session),
):
    """Verify a Google credential and return a JWT access token.

    If the user doesn't exist, creates a new account.
    If it does exist, updates email and display_name from Google.
    """
    google_payload = await verify_google_token(body.credential)

    if google_payload.get("email_verified") is not True:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="El mail de Google no está verificado")

    google_id = google_payload["sub"]
    email = normalize_email(google_payload.get("email", ""))
    display_name = google_payload.get("name")

    result = await session.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            display_name=display_name,
            google_id=google_id,
            email_verified=True,
        )
        session.add(user)
    else:
        if not user.email_verified:
            user.email_verified = True
            user.password_hash = None
        user.google_id = google_id
        user.display_name = display_name

    await session.commit()
    await session.refresh(user)

    access_token = create_access_token(user.id)
    return TokenResponse(access_token=access_token)


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def register(
    body: RegisterRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    email_sender: EmailSender = Depends(get_email_sender),
):
    email = normalize_email(body.email)
    await enforce_auth_rate_limit(request, email, "register")
    result = await session.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()
    content = None

    if user is None:
        user = User(
            email=email,
            display_name=body.name,
            password_hash=await hash_password(body.password),
            email_verified=False,
        )
        session.add(user)
        await session.flush()
        raw_token = await issue_token(session, user.id, EMAIL_VERIFICATION_PURPOSE)
        content = verification_email(raw_token)
    elif not user.email_verified:
        user.password_hash = await hash_password(body.password)
        raw_token = await issue_token(session, user.id, EMAIL_VERIFICATION_PURPOSE)
        content = verification_email(raw_token)

    await session.commit()
    if content is not None:
        schedule_email(background_tasks, email_sender, email, content)
    return {"message": GENERIC_AUTH_MESSAGE}


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(body: VerifyEmailRequest, session: AsyncSession = Depends(get_session)):
    token = await consume_token(session, body.token, EMAIL_VERIFICATION_PURPOSE)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="El link de verificación no es válido o venció"
        )
    user = await session.get(User, token.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El link de verificación no es válido")
    user.email_verified = True
    await session.commit()
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    body: EmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    email_sender: EmailSender = Depends(get_email_sender),
):
    email = normalize_email(body.email)
    await enforce_auth_rate_limit(request, email, "resend-verification")
    result = await session.execute(select(User).where(User.email == email, User.email_verified.is_(False)))
    user = result.scalar_one_or_none()
    if user is not None:
        raw_token = await issue_token(session, user.id, EMAIL_VERIFICATION_PURPOSE)
        await session.commit()
        schedule_email(background_tasks, email_sender, email, verification_email(raw_token))
    return {"message": GENERIC_AUTH_MESSAGE}


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)):
    email = normalize_email(body.email)
    await enforce_auth_rate_limit(request, email, "login")
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or user.password_hash is None:
        await verify_dummy_password(body.password)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    if not await verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "email_not_verified", "message": "Verificá tu mail antes de iniciar sesión"},
        )
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    body: EmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    email_sender: EmailSender = Depends(get_email_sender),
):
    email = normalize_email(body.email)
    await enforce_auth_rate_limit(request, email, "forgot-password")
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        raw_token = await issue_token(session, user.id, PASSWORD_RESET_PURPOSE)
        await session.commit()
        schedule_email(background_tasks, email_sender, email, password_reset_email(raw_token))
    return {"message": PASSWORD_RESET_MESSAGE}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, session: AsyncSession = Depends(get_session)):
    token = await consume_token(session, body.token, PASSWORD_RESET_PURPOSE)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="El link de recuperación no es válido o venció"
        )
    user = await session.get(User, token.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El link de recuperación no es válido")
    user.password_hash = await hash_password(body.new_password)
    user.email_verified = True
    await session.commit()
    return {"message": "Contraseña actualizada correctamente"}


@router.post("/set-password")
async def set_password(
    body: SetPasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if current_user.password_hash is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya tenés una contraseña configurada")
    current_user.password_hash = await hash_password(body.new_password)
    await session.commit()
    return {"message": "Contraseña configurada correctamente"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return current_user


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(
    body: DevAuthRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create or reuse a local development user and return a JWT access token.

    This endpoint is only available when DEV_AUTH_MODE is enabled.
    """
    if not settings.DEV_AUTH_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development authentication mode is disabled",
        )

    email = body.email.strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required",
        )

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            display_name=body.display_name,
            google_id=f"dev-local:{email}",
        )
        session.add(user)
    elif body.display_name:
        user.display_name = body.display_name

    await session.commit()
    await session.refresh(user)

    access_token = create_access_token(user.id)
    return TokenResponse(access_token=access_token)
