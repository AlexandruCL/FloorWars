"""RFC 9457 problem details (``application/problem+json``), the error format of the contract.

Routes and services signal an error by raising ``ProblemError`` (or one of the helpers below);
``install_problem_handlers`` turns it, FastAPI validation errors (422) and plain HTTP errors
(404, 405, ...) into a ``Problem`` body. Unexpected exceptions become a 500 problem without
any detail, and the exception itself is logged by the server.

Usage from any route or service::

    from app.api.problems import ProblemError, not_found

    raise not_found("No such season.")
    raise ProblemError(409, "Already joined", type_="urn:floorwars:problem:already-joined")

``type`` is ``about:blank`` unless a route needs a machine-readable reason: then use a
``urn:floorwars:problem:<slug>`` URN (RFC 9457 allows non-dereferenceable type URIs) and list it
in the route's docstring. Never put secrets, codes or tokens in ``detail``.
"""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"
ABOUT_BLANK = "about:blank"


class Problem(BaseModel):
    """RFC 9457 problem details body. Extension members are allowed (``extra="allow"``)."""

    model_config = ConfigDict(extra="allow")

    type: str = ABOUT_BLANK
    title: str
    status: int = Field(ge=100, le=599)
    detail: str | None = None
    instance: str | None = None


class ProblemError(Exception):
    """Raise to answer with a ``Problem``. ``extensions`` become extra members of the body."""

    def __init__(
        self,
        status: int,
        title: str | None = None,
        detail: str | None = None,
        *,
        type_: str = ABOUT_BLANK,
        headers: Mapping[str, str] | None = None,
        **extensions: Any,
    ) -> None:
        self.problem = Problem(
            type=type_,
            title=title or HTTPStatus(status).phrase,
            status=status,
            detail=detail,
            **extensions,
        )
        self.headers = dict(headers or {})
        super().__init__(self.problem.title)


def problem_response(
    status: int,
    title: str | None = None,
    detail: str | None = None,
    *,
    type_: str = ABOUT_BLANK,
    headers: Mapping[str, str] | None = None,
    **extensions: Any,
) -> JSONResponse:
    """Build a ``JSONResponse`` with media type ``application/problem+json``."""
    err = ProblemError(status, title, detail, type_=type_, headers=headers, **extensions)
    return _render(err)


def _render(err: ProblemError) -> JSONResponse:
    return JSONResponse(
        err.problem.model_dump(mode="json", exclude_none=True),
        status_code=err.problem.status,
        headers=err.headers,
        media_type=PROBLEM_JSON,
    )


def problem_doc(description: str) -> dict[str, Any]:
    """OpenAPI entry for a route: ``responses={409: problem_doc("Already joined.")}``."""
    return {
        "description": description,
        "content": {PROBLEM_JSON: {"schema": Problem.model_json_schema()}},
    }


# Helpers for the common cases. Each returns the error; the caller raises it.


def unauthorized(detail: str = "Missing, invalid or expired credentials.") -> ProblemError:
    """401 with ``WWW-Authenticate: Bearer`` (RFC 6750)."""
    return ProblemError(401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def forbidden(detail: str, *, type_: str = ABOUT_BLANK) -> ProblemError:
    return ProblemError(403, detail=detail, type_=type_)


def not_found(detail: str = "No such resource.") -> ProblemError:
    return ProblemError(404, detail=detail)


def conflict(detail: str, *, type_: str = ABOUT_BLANK) -> ProblemError:
    return ProblemError(409, detail=detail, type_=type_)


def too_many_requests(detail: str, retry_after_s: int | None = None) -> ProblemError:
    """429, with ``Retry-After`` in whole seconds when known (contract ``TooManyRequests``)."""
    headers = {"Retry-After": str(max(1, retry_after_s))} if retry_after_s is not None else None
    return ProblemError(429, detail=detail, headers=headers)


def service_unavailable(detail: str) -> ProblemError:
    return ProblemError(503, detail=detail)


# Exception handlers.


async def _problem_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return _render(cast(ProblemError, exc))


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Only location, message and error type: pydantic's ``input`` and ``ctx`` would echo the
    # submitted values back (and into any log of the response), for example an OTP code.
    errors = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in cast(RequestValidationError, exc).errors()
    ]
    return problem_response(422, detail="The request does not match the schema.", errors=errors)


async def _http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, exc)
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem_response(exc.status_code, detail=detail, headers=exc.headers)


async def _unhandled_error_handler(_: Request, __: Exception) -> JSONResponse:
    return problem_response(500)


def install_problem_handlers(app: FastAPI) -> None:
    """Register the handlers that render every error as ``application/problem+json``."""
    app.add_exception_handler(ProblemError, _problem_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
