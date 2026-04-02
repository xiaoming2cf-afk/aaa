from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LibraryStatus:
    name: str
    available: bool
    version: str = ""
    note: str = ""


def _package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return ""


def get_library_statuses() -> dict[str, LibraryStatus]:
    statuses: dict[str, LibraryStatus] = {}
    checks = {
        "statsmodels": ("statsmodels", "statsmodels"),
        "linearmodels": ("linearmodels", "linearmodels"),
        "arch": ("arch", "arch"),
        "causalpy": ("causalpy", "causalpy"),
        "pymc": ("pymc", "pymc"),
        "arviz": ("arviz", "arviz"),
        "pypfopt": ("pypfopt", "PyPortfolioOpt"),
        "lightgbm": ("lightgbm", "lightgbm"),
        "catboost": ("catboost", "catboost"),
    }
    for slug, (module_name, dist_name) in checks.items():
        try:
            import_module(module_name)
            statuses[slug] = LibraryStatus(
                name=slug,
                available=True,
                version=_package_version(dist_name),
            )
        except Exception as exc:  # pragma: no cover - optional dependency discovery
            statuses[slug] = LibraryStatus(
                name=slug,
                available=False,
                version="",
                note=str(exc),
            )
    statuses["qlib"] = _probe_qlib_status()
    return statuses


def _probe_qlib_status() -> LibraryStatus:
    try:
        import_module("qlib")
    except Exception as exc:  # pragma: no cover - optional dependency discovery
        fallback_root = Path(__file__).resolve().parents[2] / "_import" / "model_libs" / "qlib-main"
        if fallback_root.exists():
            return LibraryStatus(
                name="qlib",
                available=True,
                version=_package_version("pyqlib"),
                note=f"Native qlib runtime is unstable in this environment; using qlib-inspired local fallback. Import issue: {exc}",
            )
        return LibraryStatus(name="qlib", available=False, note=str(exc))
    try:
        import_module("qlib.contrib.model.linear")
        import_module("qlib.contrib.model.gbdt")
        return LibraryStatus(name="qlib", available=True, version=_package_version("pyqlib"))
    except Exception as exc:  # pragma: no cover - optional dependency discovery
        return LibraryStatus(
            name="qlib",
            available=True,
            version=_package_version("pyqlib"),
            note=f"Core package imports but contrib runtime is unstable; using qlib-inspired local fallback. Runtime note: {exc}",
        )


def get_library_status(slug: str) -> LibraryStatus:
    return get_library_statuses().get(slug, LibraryStatus(name=slug, available=False))


ENGINE_LABELS = {
    "baseline": "Baseline",
    "statsmodels": "statsmodels",
    "linearmodels": "linearmodels",
    "arch": "arch",
    "causalpy": "CausalPy",
    "pymc": "PyMC",
    "pypfopt": "PyPortfolioOpt",
    "qlib": "Qlib-style Quant",
    "catboost": "CatBoost",
}


def engine_label(engine: str) -> str:
    return ENGINE_LABELS.get(engine, engine)


def engine_metadata(engine: str, *, async_only: bool = False, optional: bool = False) -> dict[str, Any]:
    status = get_library_status(engine if engine != "pypfopt" else "pypfopt")
    return {
        "engine": engine,
        "engine_label": engine_label(engine),
        "engine_available": status.available,
        "engine_version": status.version,
        "engine_note": status.note,
        "async_only": async_only,
        "requires_optional_dependency": optional,
    }
