from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from .identifier import IdentifierKind, ResolvedIdentifier
from .models import User


_IDENTIFIER_COLUMNS = {
    IdentifierKind.EMAIL: User.email_normalized,
    IdentifierKind.PHONE: User.phone_e164,
    IdentifierKind.USERNAME: User.username_normalized,
}


def user_lookup_query(identifier: ResolvedIdentifier) -> Select[tuple[User]]:
    """Build a parameterized query against only the resolved identifier column."""
    column = _IDENTIFIER_COLUMNS[identifier.kind]
    return select(User).where(column == identifier.value).limit(1)


async def find_user_by_identifier(
    session: AsyncSession, identifier: ResolvedIdentifier
) -> User | None:
    result = await session.execute(user_lookup_query(identifier))
    return result.scalar_one_or_none()
