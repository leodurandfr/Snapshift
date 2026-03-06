from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

security = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    token: str | None = Query(default=None, alias="token"),
) -> str:
    # Check Bearer header first, then query param (for <img src> and downloads)
    if credentials and credentials.credentials == settings.api_token:
        return credentials.credentials
    if token and token == settings.api_token:
        return token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


AuthToken = Annotated[str, Depends(verify_token)]
