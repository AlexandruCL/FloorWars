"""Auth integration tests also need Valkey (rate limits): skip them when it is not configured."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from tests.helpers import TEST_VALKEY_URL


@pytest.fixture
def make_app(make_app: Callable[..., TestClient]) -> Callable[..., TestClient]:
    if not TEST_VALKEY_URL:
        pytest.skip("FLOORWARS_TEST_VALKEY_URL not set")
    return make_app
