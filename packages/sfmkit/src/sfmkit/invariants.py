"""Declarative payload invariants.

Schemas reference these by name rather than embedding expressions, so no schema
file ever gets evaluated as code:

    invariants:
      - check: no_nan
        args: {file: observations, array: obs}
      - check: max_plus_one_equals
        args: {file: observations, array: obs, column: 0, scalar: track_count}

Adding a check is adding a function and one REGISTRY entry. Checks return None
when satisfied and a human-readable problem string when not.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

# A resolver hands a check the concrete array for (file, array) names.
Resolver = Callable[[str, str], "np.ndarray | None"]

CheckFn = Callable[..., "str | None"]


def _get(resolve: Resolver, file: str, array: str) -> "np.ndarray | None":
    return resolve(file, array)


def no_nan(resolve: Resolver, *, file: str, array: str) -> str | None:
    a = _get(resolve, file, array)
    if a is None:
        return None  # presence is the schema's job, not ours
    if np.issubdtype(a.dtype, np.floating) and np.isnan(a).any():
        n = int(np.isnan(a).sum())
        return f"{file}/{array} contains {n} NaN value(s)"
    return None


def finite(resolve: Resolver, *, file: str, array: str) -> str | None:
    a = _get(resolve, file, array)
    if a is None:
        return None
    if np.issubdtype(a.dtype, np.floating) and not np.isfinite(a).all():
        n = int((~np.isfinite(a)).sum())
        return f"{file}/{array} contains {n} non-finite value(s) (NaN or inf)"
    return None


def nonempty(resolve: Resolver, *, file: str, array: str) -> str | None:
    a = _get(resolve, file, array)
    if a is None:
        return None
    if a.size == 0:
        return f"{file}/{array} is empty"
    return None


def max_plus_one_equals(
    resolve: Resolver,
    *,
    file: str,
    array: str,
    column: int,
    scalar: str,
    scalar_file: str | None = None,
) -> str | None:
    """Check that ids in a column are 0..N-1 dense, where N is a scalar array.

    Catches the classic off-by-one between an observation table and its declared
    count, which otherwise shows up as an index error three stages downstream.
    """
    a = _get(resolve, file, array)
    n = _get(resolve, scalar_file or file, scalar)
    if a is None or n is None or a.size == 0:
        return None
    if a.ndim < 2 or a.shape[1] <= column:
        return None  # a shape problem; the structural check owns that message
    observed = int(np.max(a[:, column])) + 1
    declared = int(n)
    if observed != declared:
        return (
            f"{file}/{array} column {column} implies {observed} distinct ids "
            f"but {scalar} declares {declared}"
        )
    return None


def values_within(
    resolve: Resolver,
    *,
    file: str,
    array: str,
    minimum: float | None = None,
    maximum: float | None = None,
    column: int | None = None,
) -> str | None:
    a = _get(resolve, file, array)
    if a is None or a.size == 0:
        return None
    view = a if column is None else a[:, column]
    where = f"{file}/{array}" + (f" column {column}" if column is not None else "")
    if minimum is not None and float(np.min(view)) < minimum:
        return f"{where} has minimum {float(np.min(view))}, below the allowed {minimum}"
    if maximum is not None and float(np.max(view)) > maximum:
        return f"{where} has maximum {float(np.max(view))}, above the allowed {maximum}"
    return None


def same_length(
    resolve: Resolver, *, file: str, arrays: list[str]
) -> str | None:
    lengths = {}
    for name in arrays:
        a = _get(resolve, file, name)
        if a is not None:
            lengths[name] = int(a.shape[0]) if a.ndim else 1
    if len(set(lengths.values())) > 1:
        detail = ", ".join(f"{k}={v}" for k, v in sorted(lengths.items()))
        return f"{file} arrays disagree on length: {detail}"
    return None


REGISTRY: dict[str, CheckFn] = {
    "no_nan": no_nan,
    "finite": finite,
    "nonempty": nonempty,
    "max_plus_one_equals": max_plus_one_equals,
    "values_within": values_within,
    "same_length": same_length,
}
