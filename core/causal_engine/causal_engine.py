# -*- coding: utf-8 -*-
import warnings
warnings.warn(
    "Import from this module is deprecated. Use core.causal.causal_engine.CausalEngine instead.",
    DeprecationWarning,
    stacklevel=2,
)
from core.causal.causal_engine import CausalEngine  # noqa: F401
