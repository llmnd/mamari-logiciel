import uuid
from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mamari_api.core.database import get_session
from mamari_api.modules.identity.models import Membership, Organization, User
from mamari_api.modules.identity.security import decode_access_token

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    access_token: Annotated[str | None, Cookie()] = None,
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise.",
        headers={"WWW-Authenticate": "Cookie"},
    )
    if access_token is None:
        raise unauthorized

    try:
        user_id = decode_access_token(access_token)
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized from None

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_optional_current_user(
    session: SessionDep,
    access_token: Annotated[str | None, Cookie()] = None,
) -> User | None:
    if access_token is None:
        return None

    try:
        user_id = decode_access_token(access_token)
    except (jwt.InvalidTokenError, ValueError):
        return None

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


OptionalCurrentUserDep = Annotated[User | None, Depends(get_optional_current_user)]


class CurrentMembership:
    def __init__(self, user: User, organization: Organization, membership: Membership) -> None:
        self.user = user
        self.organization = organization
        self.membership = membership


async def get_current_membership(
    session: SessionDep,
    user: CurrentUserDep,
    organization_id: Annotated[uuid.UUID, Header(alias="X-Organization-ID")],
) -> CurrentMembership:
    result = await session.execute(
        select(Membership, Organization)
        .join(Organization, Membership.organization_id == Organization.id)
        .where(
            Membership.user_id == user.id,
            Membership.organization_id == organization_id,
            Membership.is_active.is_(True),
            Organization.is_active.is_(True),
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'avez pas accès à cette organisation.",
        )
    membership, organization = row
    return CurrentMembership(user, organization, membership)


def require_roles(*roles: str) -> Callable[..., CurrentMembership]:
    allowed_roles = frozenset(roles)

    async def dependency(
        context: Annotated[CurrentMembership, Depends(get_current_membership)],
    ) -> CurrentMembership:
        if context.membership.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Votre rôle ne permet pas cette action.",
            )
        return context

    return dependency
