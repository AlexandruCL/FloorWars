"""Request and response bodies of ``/v1/auth/*`` (contract 0.4.0-draft schemas of the same name).

Unknown fields are rejected (``additionalProperties: false`` in the contract). Booleans and
strings are strict, so ``"yes"`` or ``1`` is not a boolean and a number is not a code.
"""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, StringConstraints

# Pragmatic address check (the contract says ``format: email``); the domain allow-list is the
# real gate. Normalised to lower case: university mailboxes are case-insensitive. No ``+`` in
# the local part: sub-addresses would turn one mailbox into many accounts and rate-limit buckets.
Email = Annotated[
    StrictStr,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=254,
        pattern=r"^[A-Za-z0-9._%-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$",
    ),
]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OtpRequest(_Body):
    email: Email


class DeviceInfo(_Body):
    id: uuid.UUID
    model: Annotated[StrictStr, StringConstraints(strip_whitespace=True, max_length=100)]
    has_barometer: StrictBool


class OtpVerifyRequest(_Body):
    email: Email
    code: Annotated[StrictStr, StringConstraints(pattern=r"^[0-9]{6}$")]
    device: DeviceInfo
    accept_terms: StrictBool = False
    confirm_adult: StrictBool = False


class RefreshRequest(_Body):
    refresh_token: Annotated[StrictStr, StringConstraints(min_length=1, max_length=128)]


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105 (OAuth token type)
    expires_in: int = Field(ge=1)
    refresh_expires_in: int = Field(ge=1)
