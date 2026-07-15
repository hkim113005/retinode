"""Shared fixtures for NEURON-marked tests: compile mechanisms, or skip."""

import importlib.util

import pytest

from engine.cable import _neuron


def pytest_runtest_setup(item):
    # Skip NEURON-marked tests when NEURON isn't installed (fast/dev environments).
    if "neuron" in item.keywords and importlib.util.find_spec("neuron") is None:
        pytest.skip("NEURON not installed (install the 'cable' extra)")


@pytest.fixture(scope="session")
def neuron_h():
    """Compiled-and-loaded NEURON ``h``, or skip if it can't be built."""
    try:
        return _neuron.load()
    except Exception as exc:  # toolchain / compilation failure
        pytest.skip(f"NEURON mechanisms unavailable: {exc}")
