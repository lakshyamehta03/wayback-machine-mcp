import pytest

from wayback_mcp.client import http as _http_module


@pytest.fixture(autouse=True)
def _clear_response_cache():
    _http_module._response_cache.clear()
    yield
    _http_module._response_cache.clear()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests against live IA endpoints",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--integration"):
        return
    skip = pytest.mark.skip(reason="pass --integration to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
