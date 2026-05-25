from importlib import import_module
from typing import Any

__all__ = ["app"]


def __getattr__(name: str) -> Any:
	if name == "app":
		return import_module("tc_api.trucon.app").app
	raise AttributeError(f"module 'tc_api.trucon' has no attribute {name!r}")