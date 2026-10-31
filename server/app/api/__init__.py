"""HTTP layer: versioned routers, shared dependencies and RFC 9457 problem details.

- ``app.api.v1``: the ``/v1`` router; each feature adds one module (``auth``, ``teams``, ...).
- ``app.api.deps``: dependencies shared by routes (``current_user``, ``DbSession``, ...).
- ``app.api.problems``: ``ProblemError`` and the exception handlers.
"""
