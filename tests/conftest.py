import os

import pytest_asyncio

os.environ.setdefault("R2_ACCOUNT_ID", "test-account")
os.environ.setdefault("R2_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("R2_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("R2_BUCKET_NAME", "test-bucket")


@pytest_asyncio.fixture(autouse=True)
async def reset_database_engine():
    from app.database import engine

    await engine.dispose()
    yield
    await engine.dispose()
