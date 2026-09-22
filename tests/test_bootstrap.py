"""Verify that the development installation exposes the project package."""

from importlib import import_module
from importlib.metadata import distribution


def test_installed_package_is_importable() -> None:
    package = import_module("asset_copilot")

    assert package.__name__ == "asset_copilot"
    assert distribution("ai-asset-copilot").metadata["Name"] == "ai-asset-copilot"
