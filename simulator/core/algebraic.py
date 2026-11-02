from __future__ import annotations

import math
import sys
from typing import Callable

_EPS = sys.float_info.epsilon


def bracketed_newton(
    residual_gradient: Callable[[float], tuple[float, float]],
    lower: float,
    upper: float,
    initial: float,
    *,
    tolerance: float,
    max_iterations: int,
) -> tuple[float, int, bool]:
    """Solve a scalar balance inside a sign-changing physical bracket."""
    f_lower = residual_gradient(lower)[0]
    f_upper = residual_gradient(upper)[0]
    if not (math.isfinite(f_lower) and math.isfinite(f_upper)):
        return math.nan, 0, False
    if abs(f_lower) <= tolerance:
        return lower, 0, True
    if abs(f_upper) <= tolerance:
        return upper, 0, True
    if (f_lower > 0.0) == (f_upper > 0.0):
        return math.nan, 0, False
    value = min(max(initial, lower), upper)
    for iteration in range(1, max_iterations + 1):
        residual, gradient = residual_gradient(value)
        if math.isfinite(residual):
            if abs(residual) <= tolerance:
                return value, iteration, True
            if (residual > 0.0) == (f_lower > 0.0):
                lower, f_lower = value, residual
            else:
                upper = value
        # Numerical Recipes (Press et al., 2007), §9.4: keep Newton inside
        # a sign-changing bracket; periodic bisection guarantees contraction.
        candidate = math.nan
        if math.isfinite(residual) and math.isfinite(gradient) and gradient != 0.0:
            candidate = value - residual / gradient
        if not lower < candidate < upper or iteration % 8 == 0:
            candidate = lower + (upper - lower) * 0.5
        if candidate == value or upper - lower <= 8.0 * _EPS * max(abs(lower), abs(upper)):
            # Zero step or collapsed sign-changing bracket: the root is
            # resolved to machine precision even if |residual| > tolerance.
            return value, iteration, True
        value = candidate
    return value, max_iterations, False
