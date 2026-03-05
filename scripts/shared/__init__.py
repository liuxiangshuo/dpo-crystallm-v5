#!/usr/bin/env python3
"""
Shared utilities for CrystaLLM training pipeline.

This package contains shared modules used by multiple training scripts
to avoid code duplication and improve maintainability.
"""

__version__ = "1.0.0"

# Modules are imported on-demand to avoid heavy dependencies like torch
# when only lightweight utilities are needed.
#
# Usage:
#   from shared.lora_utils import LoRALinear, inject_lora  # requires torch
#   from shared.pipeline_utils import count_csv_rows         # no external deps
#   from shared.pair_merge import merge_pairs                # standard library only

__all__ = []
