import pytest


MARKERS = {
    "unit": "quick tests that do not require a solver, must run in <2s",
    "component": "quick tests that may require a solver",
    "integration": "long duration tests",
}


def pytest_configure(config: pytest.Config):
    for name, description in MARKERS.items():
        config.addinivalue_line("markers", f"{name}: {description}")
