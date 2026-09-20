from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("capture-api")
except PackageNotFoundError:  # pragma: no cover - only when running from a bare source tree
    __version__ = "0.0.0"

__all__ = ["__version__"]
