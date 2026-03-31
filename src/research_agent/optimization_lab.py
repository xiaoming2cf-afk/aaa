from __future__ import annotations

import importlib
import inspect
import json
import logging
import math
import multiprocessing as mp
import os
import pkgutil
import warnings
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from functools import lru_cache
from pathlib import Path
from types import MethodType
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import factorial as scipy_factorial
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .config import Settings
from .entities import DataAsset, KnowledgeRecord, User, Workspace
from .platform_core import (
    create_knowledge_record,
    get_owned_knowledge_record,
    save_upload_asset,
    serialize_asset,
    serialize_knowledge_record,
)
from .utils import slugify, truncate_text


DEFAULT_OPTIMIZERS = [
    "mealpy.swarm_based.PSO.OriginalPSO",
    "mealpy.evolutionary_based.DE.OriginalDE",
    "mealpy.swarm_based.WOA.OriginalWOA",
    "mealpy.swarm_based.GWO.OriginalGWO",
    "mealpy.swarm_based.HHO.OriginalHHO",
    "mealpy.physics_based.SA.OriginalSA",
]

DEFAULT_FUNCTIONS = [
    "Ackley01",
    "Alpine01",
    "Brown",
    "Cigar",
    "Griewank",
    "Salomon",
]

MEALPY_PARAMETER_OVERRIDES: dict[str, dict[str, Any]] = {
    "mealpy.bio_based.BCO.OriginalBCO": {"n_chemotaxis": 3},
    "mealpy.bio_based.IWO.OriginalIWO": {"seed_max": 4},
    "mealpy.evolutionary_based.CRO.OCRO": {"restart_count": 2},
    "mealpy.evolutionary_based.MA.OriginalMA": {"max_local_gens": 3},
    "mealpy.human_based.BSO.ImprovedBSO": {"m_clusters": 2},
    "mealpy.human_based.BSO.OriginalBSO": {"m_clusters": 2},
    "mealpy.human_based.CHIO.DevCHIO": {"max_age": 1},
    "mealpy.human_based.CHIO.OriginalCHIO": {"max_age": 1},
    "mealpy.human_based.GSKA.OriginalGSKA": {"kg": 1},
    "mealpy.human_based.ICA.OriginalICA": {"empire_count": 2},
    "mealpy.human_based.SARO.DevSARO": {"mu": 2},
    "mealpy.human_based.SARO.OriginalSARO": {"mu": 2},
    "mealpy.human_based.TLO.ImprovedTLO": {"n_teachers": 2},
    "mealpy.math_based.CEM.OriginalCEM": {"n_best": 2},
    "mealpy.math_based.HC.SwarmHC": {"neighbour_size": 2},
    "mealpy.swarm_based.BSA.OriginalBSA": {"ff": 2},
    "mealpy.swarm_based.EHO.OriginalEHO": {"n_clans": 2},
    "mealpy.swarm_based.WOA.HI_WOA": {"feedback_max": 2},
}

MEALPY_MIN_EPOCH: dict[str, int] = {
    "mealpy.evolutionary_based.CRO.OCRO": 4,
}

MEALPY_MIN_POP_SIZE: dict[str, int] = {
    "mealpy.human_based.GSKA.OriginalGSKA": 20,
    "mealpy.human_based.GSKA.DevGSKA": 20,
}

MEALPY_DISABLED_OPTIMIZERS: dict[str, str] = {
    "mealpy.bio_based.BCO.OriginalBCO": (
        "Disabled due to an upstream Mealpy bug: the implementation references undefined attributes "
        "such as self.dim/self.positions during evolve()."
    ),
}

MEALPY_PATCH_NOTES: dict[str, str] = {
    "mealpy.physics_based.ESO.OriginalESO": (
        "Applies a runtime safeguard that clips the percentile threshold used to detect ionized regions, "
        "preventing invalid percentile values above 100."
    ),
}

OPFUNU_ABSTRACT_NAMES = {"Benchmark", "CecBenchmark"}
OPFUNU_DIMENSION_CANDIDATES = (30, 10, 50, 100, 5, 2)
MAX_PARALLEL_TASKS = 240
MAX_ESTIMATED_EVALUATIONS = 5_000_000


def _ensure_numpy_compat_aliases() -> None:
    if not hasattr(np, "factorial"):
        np.factorial = scipy_factorial  # type: ignore[attr-defined]
    if not hasattr(np, "p"):
        np.p = np.pi  # type: ignore[attr-defined]


def _can_use_process_pool() -> bool:
    main_file = getattr(__import__("__main__"), "__file__", "")
    if not main_file or str(main_file).startswith("<"):
        return False
    try:
        return mp.get_start_method(allow_none=True) in {None, "spawn", "fork", "forkserver"}
    except Exception:
        return False


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    return value


def _safe_float(value: Any, default: float = float("nan")) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _ensure_array(value: Any, *, fallback: float, size: int) -> np.ndarray:
    array = np.asarray(value, dtype=float) if value is not None else np.asarray([], dtype=float)
    if array.size == 0:
        return np.full(size, fallback, dtype=float)
    if array.size == 1:
        return np.full(size, float(array.item()), dtype=float)
    if array.size != size:
        return np.resize(array, size).astype(float)
    return array.astype(float)


def _effective_epoch(optimizer_name: str, epoch: int) -> int:
    return max(int(epoch), MEALPY_MIN_EPOCH.get(optimizer_name, 1))


def _effective_pop_size(optimizer_name: str, pop_size: int) -> int:
    return max(int(pop_size), MEALPY_MIN_POP_SIZE.get(optimizer_name, 5))


def _get_optimizer_class(optimizer_name: str):
    module_name, class_name = optimizer_name.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def _get_function_class(function_name: str):
    from opfunu import ALL_DATABASE

    for name, cls in ALL_DATABASE:
        if name == function_name:
            return cls
    raise KeyError(f"Unknown opfunu function: {function_name}")


def _iter_mealpy_optimizer_classes():
    import mealpy
    from mealpy.optimizer import Optimizer

    seen: set[str] = set()
    for module_info in pkgutil.walk_packages(mealpy.__path__, prefix="mealpy."):
        module_name = module_info.name
        if ".utils" in module_name or module_name.endswith(".optimizer"):
            continue
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if not issubclass(cls, Optimizer) or cls is Optimizer:
                continue
            if cls.__module__ != module_name:
                continue
            fqcn = f"{cls.__module__}.{cls.__name__}"
            if fqcn in seen:
                continue
            seen.add(fqcn)
            yield fqcn, cls


def _probe_function_instance(function_name: str, preferred_dimension: int | None = None) -> tuple[Any, dict[str, Any]]:
    _ensure_numpy_compat_aliases()
    cls = _get_function_class(function_name)
    probe_errors: list[str] = []
    dimensions = []
    if preferred_dimension:
        dimensions.append(int(preferred_dimension))
    dimensions.extend(value for value in OPFUNU_DIMENSION_CANDIDATES if value not in dimensions)
    for candidate in dimensions:
        try:
            with redirect_stdout(StringIO()), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                instance = cls(ndim=candidate)
            resolved_ndim = int(getattr(instance, "ndim", candidate))
            vector = np.zeros(resolved_ndim, dtype=float)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitness = _safe_float(instance.evaluate(vector))
            lb = _ensure_array(getattr(instance, "lb", None), fallback=-100.0, size=resolved_ndim)
            ub = _ensure_array(getattr(instance, "ub", None), fallback=100.0, size=resolved_ndim)
            return instance, {
                "name": function_name,
                "dimension": resolved_ndim,
                "requested_dimension": candidate,
                "lower_bound_preview": lb[: min(5, resolved_ndim)].tolist(),
                "upper_bound_preview": ub[: min(5, resolved_ndim)].tolist(),
                "baseline_fitness": fitness,
            }
        except Exception as exc:
            probe_errors.append(f"ndim={candidate}: {exc}")
    raise ValueError("; ".join(probe_errors) or f"Unable to instantiate {function_name}")


def _instantiate_optimizer(optimizer_name: str, *, epoch: int, pop_size: int, seed: int):
    if optimizer_name in MEALPY_DISABLED_OPTIMIZERS:
        raise ValueError(MEALPY_DISABLED_OPTIMIZERS[optimizer_name])
    cls = _get_optimizer_class(optimizer_name)
    kwargs = {
        "epoch": _effective_epoch(optimizer_name, epoch),
        "pop_size": _effective_pop_size(optimizer_name, pop_size),
        "seed": int(seed),
    }
    kwargs.update(MEALPY_PARAMETER_OVERRIDES.get(optimizer_name, {}))
    optimizer = cls(**kwargs)
    _apply_optimizer_runtime_patch(optimizer_name, optimizer)
    try:
        optimizer.logger.disabled = True
    except Exception:
        pass
    try:
        logging.getLogger(optimizer_name).disabled = True
        logging.getLogger(optimizer_name).setLevel(logging.CRITICAL)
    except Exception:
        pass
    return optimizer, kwargs


def _apply_optimizer_runtime_patch(optimizer_name: str, optimizer: Any) -> None:
    if optimizer_name == "mealpy.physics_based.ESO.OriginalESO":
        _patch_eso_optimizer(optimizer)


def _patch_eso_optimizer(optimizer: Any) -> None:
    if getattr(optimizer, "_erp_safe_patch", False):
        return

    def _safe_evolve(self, epoch: int) -> None:
        pos_pop = np.array([agent.solution for agent in self.pop])
        mean_pos = np.mean(pos_pop, axis=0)
        std_pos = np.sqrt(np.mean(np.sum((pos_pop - mean_pos) ** 2, axis=1)))
        peak_to_peak = np.max(np.max(pos_pop, axis=0) - np.min(pos_pop, axis=0))
        if peak_to_peak <= 0:
            resistance = 0.0
            ionized_pop: list[Any] = []
        else:
            resistance = std_pos / peak_to_peak
            percentile_threshold = float(np.clip((resistance / 2) * 100, 0.0, 100.0))
            fits = np.array([agent.target.fitness for agent in self.pop], dtype=float)
            fitness_percentile = np.percentile(fits, percentile_threshold)
            ionized_indices = np.where(fits <= fitness_percentile)[0]
            ionized_pop = [self.pop[idx] for idx in ionized_indices]

        if resistance <= 0:
            fc = 1.0
        else:
            try:
                exp_term = np.exp(resistance) / resistance
                log_term = np.log(1.0 - resistance) if resistance < 1 else 0.0
                beta = 1.0 / (1.0 + np.exp(-exp_term) * (resistance - abs(log_term)))
            except (OverflowError, ValueError, ZeroDivisionError):
                beta = 0.5
            try:
                fc = np.exp(resistance) + np.exp(1 - resistance) * abs(np.log(resistance)) * beta
            except (OverflowError, ValueError, ZeroDivisionError):
                fc = 1.0

        if resistance <= 0:
            fi = fc
        else:
            try:
                exp_term = np.exp(resistance) / resistance
                iter_ratio = epoch / self.epoch
                log_term = np.log(1 - iter_ratio) if iter_ratio < 1 else 0.0
                gama = 1.0 / (1.0 + np.exp(-exp_term * (resistance - abs(log_term))))
            except (OverflowError, ValueError, ZeroDivisionError):
                gama = 0.5
            fi = fc * gama

        storm_power = (resistance * fi) / fc if fc > 0 else 0.0

        pop_new = []
        for idx in range(0, self.pop_size):
            if idx == 0 or len(ionized_pop) == 0:
                agent = self.generate_empty_agent()
            else:
                alpha = ionized_pop[self.generator.integers(0, len(ionized_pop))]
                perturbation = self.generator.normal(loc=0, scale=storm_power, size=self.problem.n_dims)
                pos_new = alpha.solution + perturbation
                pos_new = self.correct_solution(pos_new)
                agent = self.generate_agent(pos_new)
            agent.target = self.get_target(agent.solution)

            in_ionized = any(np.linalg.norm(agent.solution - alpha.solution) < 0.1 for alpha in ionized_pop)
            if in_ionized:
                pos_new = agent.solution * storm_power
            elif len(ionized_pop) > 0:
                avg_ionized = np.mean([item.solution for item in ionized_pop], axis=0)
                pos_new = avg_ionized + storm_power * np.exp(fc) * self.generator.uniform(-fc, fc, self.problem.n_dims)
            else:
                pos_new = self.generator.uniform(self.problem.lb, self.problem.ub, self.problem.n_dims)
            pos_new = self.correct_solution(pos_new)
            agent_new = self.generate_agent(pos_new)
            pop_new.append(agent_new if self.compare_target(agent_new.target, agent.target) else agent)
        self.pop = pop_new

    optimizer.evolve = MethodType(_safe_evolve, optimizer)
    optimizer._erp_safe_patch = True


@lru_cache(maxsize=1)
def get_optimization_catalog() -> dict[str, Any]:
    optimizer_entries: list[dict[str, Any]] = []
    for fqcn, cls in sorted(_iter_mealpy_optimizer_classes(), key=lambda item: item[0].lower()):
        try:
            instance, kwargs = _instantiate_optimizer(fqcn, epoch=4, pop_size=12, seed=1)
            note_parts = ["Instantiation verified locally."]
            if fqcn in MEALPY_MIN_POP_SIZE:
                note_parts.append(f"Minimum pop_size enforced: {MEALPY_MIN_POP_SIZE[fqcn]}.")
            if fqcn in MEALPY_PATCH_NOTES:
                note_parts.append(MEALPY_PATCH_NOTES[fqcn])
            availability = {
                "status": "available",
                "note": " ".join(note_parts),
                "effective_epoch": kwargs["epoch"],
                "effective_pop_size": kwargs["pop_size"],
                "overrides": {key: _normalize_scalar(value) for key, value in kwargs.items() if key not in {"epoch", "pop_size", "seed"}},
            }
            del instance
        except Exception as exc:
            availability = {
                "status": "unavailable",
                "note": str(exc),
                "effective_epoch": _effective_epoch(fqcn, 4),
                "effective_pop_size": _effective_pop_size(fqcn, 12),
                "overrides": {key: _normalize_scalar(value) for key, value in MEALPY_PARAMETER_OVERRIDES.get(fqcn, {}).items()},
            }
        optimizer_entries.append(
            {
                "name": fqcn,
                "label": cls.__name__,
                "module": cls.__module__,
                "group": cls.__module__.split(".")[1] if "." in cls.__module__ else "misc",
                "availability": availability,
            }
        )

    function_entries: list[dict[str, Any]] = []
    from opfunu import ALL_DATABASE

    for function_name, _cls in sorted(ALL_DATABASE, key=lambda item: item[0].lower()):
        if function_name in OPFUNU_ABSTRACT_NAMES:
            function_entries.append(
                {
                    "name": function_name,
                    "label": function_name,
                    "module": getattr(_cls, "__module__", ""),
                    "availability": {"status": "unavailable", "note": "Abstract base entry; not a runnable benchmark."},
                }
            )
            continue
        try:
            _instance, probe = _probe_function_instance(function_name)
            function_entries.append(
                {
                    "name": function_name,
                    "label": function_name,
                    "module": getattr(_cls, "__module__", ""),
                    "dimension": probe["dimension"],
                    "availability": {"status": "available", "note": "Instantiation and baseline evaluation verified locally."},
                    "bounds": {
                        "lower": probe["lower_bound_preview"],
                        "upper": probe["upper_bound_preview"],
                    },
                    "baseline_fitness": probe["baseline_fitness"],
                }
            )
        except Exception as exc:
            function_entries.append(
                {
                    "name": function_name,
                    "label": function_name,
                    "module": getattr(_cls, "__module__", ""),
                    "availability": {"status": "unavailable", "note": str(exc)},
                }
            )

    available_optimizers = [item for item in optimizer_entries if item["availability"]["status"] == "available"]
    available_functions = [item for item in function_entries if item["availability"]["status"] == "available"]
    return {
        "optimizers": optimizer_entries,
        "functions": function_entries,
        "defaults": {
            "optimizers": [item for item in DEFAULT_OPTIMIZERS if any(entry["name"] == item for entry in available_optimizers)],
            "functions": [item for item in DEFAULT_FUNCTIONS if any(entry["name"] == item for entry in available_functions)],
        },
        "summary": {
            "optimizer_count": len(optimizer_entries),
            "optimizer_available_count": len(available_optimizers),
            "function_count": len(function_entries),
            "function_available_count": len(available_functions),
        },
    }


def list_optimization_results(db: Session, *, user: User, workspace: Workspace, limit: int = 20) -> list[KnowledgeRecord]:
    rows = list(
        db.scalars(
            select(KnowledgeRecord)
            .where(
                and_(
                    KnowledgeRecord.owner_user_id == user.id,
                    KnowledgeRecord.workspace_id == workspace.id,
                )
            )
            .order_by(KnowledgeRecord.updated_at.desc())
        )
    )
    output: list[KnowledgeRecord] = []
    for row in rows:
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        if metadata.get("workflow_type") == "optimization":
            output.append(row)
        if len(output) >= max(1, int(limit)):
            break
    return output


def _build_problem(function_name: str, requested_dimension: int) -> tuple[dict[str, Any], dict[str, Any]]:
    from mealpy import FloatVar

    function, probe = _probe_function_instance(function_name, requested_dimension)
    dimension = int(probe["dimension"])
    lb = _ensure_array(getattr(function, "lb", None), fallback=-100.0, size=dimension)
    ub = _ensure_array(getattr(function, "ub", None), fallback=100.0, size=dimension)
    bounds = FloatVar(lb=lb, ub=ub, name="x")
    problem = {
        "bounds": bounds,
        "minmax": "min",
        "obj_func": function.evaluate,
    }
    info = {
        "name": function_name,
        "dimension": dimension,
        "requested_dimension": requested_dimension,
        "lower_bounds": lb.tolist(),
        "upper_bounds": ub.tolist(),
    }
    return problem, info


def _run_single_optimization_task(task: dict[str, Any]) -> dict[str, Any]:
    optimizer_name = str(task["optimizer_name"])
    function_name = str(task["function_name"])
    run_index = int(task["run_index"])
    seed = int(task["seed"])
    epoch = int(task["epoch"])
    pop_size = int(task["pop_size"])
    requested_dimension = int(task["dimension"])
    try:
        problem, function_info = _build_problem(function_name, requested_dimension)
        optimizer, optimizer_kwargs = _instantiate_optimizer(optimizer_name, epoch=epoch, pop_size=pop_size, seed=seed)
        result = optimizer.solve(problem, mode="single")
        history = [float(value) for value in getattr(optimizer.history, "list_global_best_fit", [])]
        best_vector = np.asarray(result.solution, dtype=float).tolist() if getattr(result, "solution", None) is not None else []
        best_fitness = _safe_float(getattr(getattr(result, "target", None), "fitness", float("nan")))
        if math.isnan(best_fitness):
            best_fitness = _safe_float(getattr(getattr(getattr(optimizer, "g_best", None), "target", None), "fitness", float("nan")))
        return {
            "optimizer_name": optimizer_name,
            "function_name": function_name,
            "run_index": run_index,
            "seed": seed,
            "status": "ok",
            "best_fitness": best_fitness,
            "best_solution": best_vector,
            "curve": history,
            "curve_length": len(history),
            "resolved_dimension": function_info["dimension"],
            "requested_dimension": requested_dimension,
            "optimizer_kwargs": {key: _normalize_scalar(value) for key, value in optimizer_kwargs.items()},
            "function_info": function_info,
        }
    except Exception as exc:
        return {
            "optimizer_name": optimizer_name,
            "function_name": function_name,
            "run_index": run_index,
            "seed": seed,
            "status": "error",
            "error": str(exc),
            "curve": [],
            "curve_length": 0,
            "resolved_dimension": requested_dimension,
            "requested_dimension": requested_dimension,
            "optimizer_kwargs": {},
            "function_info": {"name": function_name, "dimension": requested_dimension},
        }


def _rank_table(score_frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if score_frame.empty:
        return pd.DataFrame(), {"statistic": None, "pvalue": None, "rankings": []}
    pivot = score_frame.pivot(index="function_name", columns="optimizer_name", values="mean_fitness")
    rank_frame = pivot.rank(axis=1, method="average", ascending=True)
    average_ranks = rank_frame.mean(axis=0).sort_values()
    friedman_stat = None
    friedman_pvalue = None
    if rank_frame.shape[1] >= 2 and rank_frame.shape[0] >= 2:
        friedman_stat, friedman_pvalue = stats.friedmanchisquare(*[pivot[column].fillna(pivot[column].mean()) for column in pivot.columns])
    ranking_rows = [
        {"optimizer_name": name, "average_rank": float(rank), "rank_order": index + 1}
        for index, (name, rank) in enumerate(average_ranks.items())
    ]
    ranking_frame = pd.DataFrame(ranking_rows)
    return ranking_frame, {
        "statistic": _safe_float(friedman_stat) if friedman_stat is not None else None,
        "pvalue": _safe_float(friedman_pvalue) if friedman_pvalue is not None else None,
        "rankings": ranking_rows,
    }


def _pairwise_tests(score_frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if score_frame.empty:
        return pd.DataFrame(), pd.DataFrame()
    pivot = score_frame.pivot(index="function_name", columns="optimizer_name", values="mean_fitness")
    algorithms = list(pivot.columns)
    wilcoxon_rows: list[dict[str, Any]] = []
    sign_rows: list[dict[str, Any]] = []
    for left_index, left_name in enumerate(algorithms):
        for right_name in algorithms[left_index + 1 :]:
            paired = pivot[[left_name, right_name]].dropna()
            if paired.empty:
                continue
            diffs = paired[left_name] - paired[right_name]
            non_zero = diffs[diffs != 0]
            if len(non_zero) >= 1:
                try:
                    wilcoxon = stats.wilcoxon(non_zero)
                    wilcoxon_pvalue = _safe_float(wilcoxon.pvalue)
                    wilcoxon_statistic = _safe_float(wilcoxon.statistic)
                except Exception:
                    wilcoxon_pvalue = float("nan")
                    wilcoxon_statistic = float("nan")
                positives = int((non_zero > 0).sum())
                negatives = int((non_zero < 0).sum())
                sign = stats.binomtest(min(positives, negatives), n=positives + negatives, p=0.5)
                sign_pvalue = _safe_float(sign.pvalue)
            else:
                wilcoxon_statistic = float("nan")
                wilcoxon_pvalue = float("nan")
                positives = 0
                negatives = 0
                sign_pvalue = float("nan")
            wilcoxon_rows.append(
                {
                    "algorithm_a": left_name,
                    "algorithm_b": right_name,
                    "statistic": wilcoxon_statistic,
                    "pvalue": wilcoxon_pvalue,
                }
            )
            sign_rows.append(
                {
                    "algorithm_a": left_name,
                    "algorithm_b": right_name,
                    "positive_differences": positives,
                    "negative_differences": negatives,
                    "pvalue": sign_pvalue,
                }
            )
    return pd.DataFrame(wilcoxon_rows), pd.DataFrame(sign_rows)


def _mean_curve(curves: list[list[float]]) -> list[float]:
    usable = [curve for curve in curves if curve]
    if not usable:
        return []
    max_len = max(len(curve) for curve in usable)
    padded = []
    for curve in usable:
        if len(curve) < max_len:
            curve = curve + [curve[-1]] * (max_len - len(curve))
        padded.append(curve)
    return np.asarray(padded, dtype=float).mean(axis=0).tolist()


def _figure_bytes(draw_fn) -> bytes:
    figure = plt.figure(figsize=(8.4, 5.2))
    try:
        draw_fn(figure)
        buffer = BytesIO()
        figure.tight_layout()
        figure.savefig(buffer, format="png", dpi=160, bbox_inches="tight")
        return buffer.getvalue()
    finally:
        plt.close(figure)


def _plot_average_convergence(mean_curves: dict[str, list[float]]) -> bytes:
    def draw(figure):
        axis = figure.add_subplot(1, 1, 1)
        for label, curve in mean_curves.items():
            if curve:
                axis.plot(range(1, len(curve) + 1), curve, label=label)
        axis.set_title("Average Convergence Curve")
        axis.set_xlabel("Iteration")
        axis.set_ylabel("Best fitness")
        axis.legend(fontsize=8)
        axis.grid(alpha=0.25)

    return _figure_bytes(draw)


def _plot_radar(ranking_frame: pd.DataFrame) -> bytes:
    labels = ranking_frame["optimizer_name"].tolist()
    values = ranking_frame["average_rank"].astype(float).tolist()
    if not labels:
        return b""
    angle_step = 2 * math.pi / len(labels)
    angles = [index * angle_step for index in range(len(labels))]
    values_loop = values + values[:1]
    angles_loop = angles + angles[:1]

    def draw(figure):
        axis = figure.add_subplot(1, 1, 1, polar=True)
        axis.plot(angles_loop, values_loop, linewidth=2)
        axis.fill(angles_loop, values_loop, alpha=0.15)
        axis.set_xticks(angles)
        axis.set_xticklabels(labels, fontsize=8)
        axis.set_title("Average Rank Radar")

    return _figure_bytes(draw)


def _plot_ranking_bar(ranking_frame: pd.DataFrame) -> bytes:
    def draw(figure):
        axis = figure.add_subplot(1, 1, 1)
        frame = ranking_frame.sort_values("average_rank", ascending=True)
        axis.barh(frame["optimizer_name"], frame["average_rank"], color="#244a7b")
        axis.set_title("Average Rank Ordering")
        axis.set_xlabel("Average rank (lower is better)")
        axis.invert_yaxis()
        axis.grid(alpha=0.2, axis="x")

    return _figure_bytes(draw)


def _plot_per_function_curves(function_curves: dict[str, dict[str, list[float]]]) -> dict[str, bytes]:
    outputs: dict[str, bytes] = {}
    for function_name, curves in function_curves.items():
        if not any(curves.values()):
            continue

        def draw(figure, curves=curves, function_name=function_name):
            axis = figure.add_subplot(1, 1, 1)
            for label, curve in curves.items():
                if curve:
                    axis.plot(range(1, len(curve) + 1), curve, label=label)
            axis.set_title(f"{function_name} convergence")
            axis.set_xlabel("Iteration")
            axis.set_ylabel("Best fitness")
            axis.legend(fontsize=8)
            axis.grid(alpha=0.25)

        outputs[function_name] = _figure_bytes(draw)
    return outputs


def _to_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")


def _save_generated_asset(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    filename: str,
    content: bytes,
    content_type: str,
    description: str,
    source_url: str = "",
) -> dict[str, Any]:
    asset = save_upload_asset(
        settings,
        db,
        user=user,
        workspace=workspace,
        filename=filename,
        content=content,
        content_type=content_type,
        description=description,
        source_url=source_url,
    )
    return serialize_asset(asset)


def run_optimization_suite(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    suite_label: str,
    optimizer_names: list[str],
    function_names: list[str],
    dimension: int = 30,
    epoch: int = 50,
    pop_size: int = 30,
    runs: int = 5,
    workers: int = 0,
    seed_base: int = 20260331,
) -> dict[str, Any]:
    catalog = get_optimization_catalog()
    available_optimizers = {item["name"]: item for item in catalog["optimizers"] if item["availability"]["status"] == "available"}
    available_functions = {item["name"]: item for item in catalog["functions"] if item["availability"]["status"] == "available"}
    selected_optimizers = [name for name in (optimizer_names or catalog["defaults"]["optimizers"]) if name in available_optimizers]
    selected_functions = [name for name in (function_names or catalog["defaults"]["functions"]) if name in available_functions]
    if not selected_optimizers:
        raise ValueError("No available optimization algorithms were selected.")
    if not selected_functions:
        raise ValueError("No available benchmark functions were selected.")
    total_tasks = len(selected_optimizers) * len(selected_functions) * max(1, int(runs))
    estimated_evaluations = total_tasks * max(1, int(epoch)) * max(2, int(pop_size))
    if total_tasks > MAX_PARALLEL_TASKS:
        raise ValueError(f"Requested suite creates {total_tasks} tasks. Reduce the selection below {MAX_PARALLEL_TASKS}.")
    if estimated_evaluations > MAX_ESTIMATED_EVALUATIONS:
        raise ValueError(
            f"Requested suite implies about {estimated_evaluations:,} evaluations, above the safety cap of {MAX_ESTIMATED_EVALUATIONS:,}."
        )

    task_payloads: list[dict[str, Any]] = []
    seed_counter = int(seed_base)
    for optimizer_name in selected_optimizers:
        for function_name in selected_functions:
            for run_index in range(max(1, int(runs))):
                task_payloads.append(
                    {
                        "optimizer_name": optimizer_name,
                        "function_name": function_name,
                        "run_index": run_index + 1,
                        "seed": seed_counter,
                        "epoch": int(epoch),
                        "pop_size": int(pop_size),
                        "dimension": int(dimension),
                    }
                )
                seed_counter += 1

    cpu_count = os.cpu_count() or 1
    worker_count = min(max(1, int(workers or cpu_count)), cpu_count, len(task_payloads))
    task_results: list[dict[str, Any]] = []
    if worker_count == 1:
        for payload in task_payloads:
            task_results.append(_run_single_optimization_task(payload))
    else:
        executor_cls = ProcessPoolExecutor if _can_use_process_pool() else ThreadPoolExecutor
        with executor_cls(max_workers=worker_count) as executor:
            futures = [executor.submit(_run_single_optimization_task, payload) for payload in task_payloads]
            for future in as_completed(futures):
                task_results.append(future.result())
    task_results.sort(key=lambda item: (item["function_name"], item["optimizer_name"], item["run_index"]))

    success_rows = [item for item in task_results if item["status"] == "ok"]
    if not success_rows:
        raise ValueError("Every optimization task failed. Inspect the failure table and reduce the selection.")
    result_frame = pd.DataFrame(
        [
            {
                "optimizer_name": item["optimizer_name"],
                "function_name": item["function_name"],
                "run_index": item["run_index"],
                "seed": item["seed"],
                "best_fitness": item["best_fitness"],
                "curve_length": item["curve_length"],
                "resolved_dimension": item["resolved_dimension"],
            }
            for item in success_rows
        ]
    )
    score_frame = (
        result_frame.groupby(["optimizer_name", "function_name"], as_index=False)
        .agg(
            mean_fitness=("best_fitness", "mean"),
            std_fitness=("best_fitness", "std"),
            min_fitness=("best_fitness", "min"),
            max_fitness=("best_fitness", "max"),
            run_count=("best_fitness", "count"),
        )
        .fillna(0.0)
    )
    ranking_frame, friedman_summary = _rank_table(score_frame)
    wilcoxon_frame, sign_frame = _pairwise_tests(score_frame)

    curve_frame = pd.DataFrame(
        [
            {
                "optimizer_name": item["optimizer_name"],
                "function_name": item["function_name"],
                "run_index": item["run_index"],
                "iteration": iteration + 1,
                "best_fitness": value,
            }
            for item in success_rows
            for iteration, value in enumerate(item["curve"])
        ]
    )
    mean_curves = {
        optimizer_name: _mean_curve([row["curve"] for row in success_rows if row["optimizer_name"] == optimizer_name])
        for optimizer_name in selected_optimizers
    }
    per_function_curves = {
        function_name: {
            optimizer_name: _mean_curve(
                [
                    row["curve"]
                    for row in success_rows
                    if row["function_name"] == function_name and row["optimizer_name"] == optimizer_name
                ]
            )
            for optimizer_name in selected_optimizers
        }
        for function_name in selected_functions
    }

    figure_assets: list[dict[str, Any]] = []
    table_assets: list[dict[str, Any]] = []
    suite_slug = slugify(suite_label) or "optimization-suite"
    average_curve_bytes = _plot_average_convergence(mean_curves)
    radar_bytes = _plot_radar(ranking_frame)
    ranking_bytes = _plot_ranking_bar(ranking_frame)
    if average_curve_bytes:
        figure_assets.append(
            _save_generated_asset(
                settings,
                db,
                user=user,
                workspace=workspace,
                filename=f"{suite_slug}-average-convergence.png",
                content=average_curve_bytes,
                content_type="image/png",
                description="Average convergence curve for the selected optimization suite.",
            )
        )
    if radar_bytes:
        figure_assets.append(
            _save_generated_asset(
                settings,
                db,
                user=user,
                workspace=workspace,
                filename=f"{suite_slug}-radar-ranks.png",
                content=radar_bytes,
                content_type="image/png",
                description="Radar chart of average algorithm ranks.",
            )
        )
    if ranking_bytes:
        figure_assets.append(
            _save_generated_asset(
                settings,
                db,
                user=user,
                workspace=workspace,
                filename=f"{suite_slug}-ranking-bar.png",
                content=ranking_bytes,
                content_type="image/png",
                description="Average rank ordering of the selected algorithms.",
            )
        )
    for function_name, image_bytes in _plot_per_function_curves(per_function_curves).items():
        figure_assets.append(
            _save_generated_asset(
                settings,
                db,
                user=user,
                workspace=workspace,
                filename=f"{suite_slug}-{slugify(function_name)}-curve.png",
                content=image_bytes,
                content_type="image/png",
                description=f"Average convergence curve for {function_name}.",
            )
        )

    for filename, frame, description in [
        (f"{suite_slug}-scores.csv", score_frame, "Mean fitness table by algorithm and benchmark."),
        (f"{suite_slug}-ranks.csv", ranking_frame, "Average rank table derived from per-function mean fitness."),
        (f"{suite_slug}-wilcoxon.csv", wilcoxon_frame, "Pairwise Wilcoxon signed-rank test table."),
        (f"{suite_slug}-sign-test.csv", sign_frame, "Pairwise sign-test table."),
        (f"{suite_slug}-curves.csv", curve_frame, "Raw iteration-by-iteration convergence data for every task."),
        (f"{suite_slug}-runs.csv", pd.DataFrame(task_results), "Raw per-run optimization output."),
    ]:
        table_assets.append(
            _save_generated_asset(
                settings,
                db,
                user=user,
                workspace=workspace,
                filename=filename,
                content=_to_csv_bytes(frame),
                content_type="text/csv",
                description=description,
            )
        )

    summary_payload = {
        "suite_label": suite_label,
        "algorithm_count": len(selected_optimizers),
        "function_count": len(selected_functions),
        "run_count": int(runs),
        "task_count": len(task_payloads),
        "worker_count": worker_count,
        "estimated_evaluations": estimated_evaluations,
        "success_count": len(success_rows),
        "failure_count": len(task_results) - len(success_rows),
        "friedman": friedman_summary,
    }
    top_rank = ranking_frame.iloc[0].to_dict() if not ranking_frame.empty else {}
    top_text = (
        f"Top algorithm by average rank: {top_rank.get('optimizer_name', 'n/a')} "
        f"(rank {top_rank.get('average_rank', 'n/a')})."
    )
    content = "\n".join(
        [
            f"# Optimization Lab | {suite_label}",
            "",
            f"- Algorithms: {len(selected_optimizers)}",
            f"- Benchmarks: {len(selected_functions)}",
            f"- Runs per pair: {runs}",
            f"- Parallel workers: {worker_count}",
            f"- Successful tasks: {len(success_rows)} / {len(task_payloads)}",
            "",
            top_text,
        ]
    )
    metadata = {
        "workflow_type": "optimization",
        "module": "optimization_lab",
        "suite_label": suite_label,
        "summary": summary_payload,
        "config": {
            "optimizer_names": selected_optimizers,
            "function_names": selected_functions,
            "dimension": int(dimension),
            "epoch": int(epoch),
            "pop_size": int(pop_size),
            "runs": int(runs),
            "worker_count": worker_count,
            "seed_base": int(seed_base),
        },
        "tables_preview": score_frame.head(50).to_dict(orient="records"),
        "ranking_preview": ranking_frame.head(20).to_dict(orient="records"),
        "failures": [item for item in task_results if item["status"] != "ok"],
        "artifacts": {
            "figures": figure_assets,
            "tables": table_assets,
        },
    }
    record = create_knowledge_record(
        db,
        user=user,
        workspace=workspace,
        title=f"Optimization Suite | {suite_label}",
        content=content,
        tags=["optimization", "mealpy", "opfunu", "parallel"],
        metadata=metadata,
    )
    record.metadata_json = {
        **(record.metadata_json or {}),
        "workflow_type": "optimization",
        "result_record_id": record.id,
        "result_detail_path": f"/data-lab/results/optimization/{record.id}",
    }
    db.flush()
    return build_optimization_result_detail(db, user=user, record_id=record.id)


def build_optimization_result_detail(db: Session, *, user: User, record_id: str) -> dict[str, Any]:
    record = get_owned_knowledge_record(db, user=user, record_id=record_id)
    metadata = dict(record.metadata_json or {})
    if metadata.get("workflow_type") != "optimization":
        raise ValueError("This knowledge record is not an optimization result.")
    artifacts = metadata.get("artifacts", {}) if isinstance(metadata.get("artifacts"), dict) else {}
    return {
        "record": serialize_knowledge_record(record),
        "result": {
            **metadata,
            "workflow_type": "optimization",
            "result_record_id": record.id,
            "result_detail_path": metadata.get("result_detail_path") or f"/data-lab/results/optimization/{record.id}",
            "artifacts": artifacts,
        },
        "workspace_id": record.workspace_id,
    }


def serialize_optimization_result_list(rows: list[KnowledgeRecord]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        item = serialize_knowledge_record(row, include_content=False)
        item["workflow_type"] = "optimization"
        item["summary"] = metadata.get("summary", {})
        item["suite_label"] = metadata.get("suite_label", row.title)
        item["result_detail_path"] = metadata.get("result_detail_path", f"/data-lab/results/optimization/{row.id}")
        items.append(item)
    return items
