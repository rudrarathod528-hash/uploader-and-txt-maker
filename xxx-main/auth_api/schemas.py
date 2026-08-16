from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints


Identifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=320),
]


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: Identifier
    password: SecretStr = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    success: Literal[True] = True
    tokenType: Literal["Bearer"] = "Bearer"
    accessToken: str
    refreshToken: str
    expiresIn: int


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    error: ErrorBody
