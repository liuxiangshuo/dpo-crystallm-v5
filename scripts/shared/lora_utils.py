#!/usr/bin/env python3
"""
LoRA (Low-Rank Adaptation) utilities for CrystaLLM training.

This module provides shared LoRA implementation used by both SFT and DPO
training scripts to avoid code duplication.

Usage:
    from shared.lora_utils import LoRALinear, inject_lora, merge_lora_state_dict

    # Inject LoRA into a model
    lora_params = inject_lora(model, rank=16, alpha=32, target_names=("c_attn",))

    # Merge LoRA weights back into base model for saving
    merged_state_dict = merge_lora_state_dict(model)
"""

import torch


class LoRALinear(torch.nn.Module):
    """Drop-in replacement for nn.Linear with low-rank adapters.

    Implements LoRA (Low-Rank Adaptation) as described in Hu et al. 2021.
    The forward pass computes: output = W*x + (B*A)*x * (alpha/rank)

    Args:
        orig: Original nn.Linear layer to wrap
        rank: LoRA rank (r), controls the size of low-rank matrices A and B
        alpha: LoRA scaling factor, the effective scaling is alpha/rank

    Attributes:
        orig: Frozen original linear layer
        lora_A: Low-rank matrix A (shape: rank x in_features)
        lora_B: Low-rank matrix B (shape: out_features x rank)
        scale: Effective scaling factor (alpha / rank)
    """

    def __init__(self, orig: torch.nn.Linear, rank: int = 16, alpha: int = 32):
        super().__init__()
        self.orig = orig
        # Freeze original weights
        self.orig.weight.requires_grad_(False)
        if self.orig.bias is not None:
            self.orig.bias.requires_grad_(False)

        d_out, d_in = orig.weight.shape
        device = orig.weight.device

        # Initialize LoRA matrices
        # A: Gaussian initialization (rank x in_features)
        self.lora_A = torch.nn.Parameter(torch.randn(rank, d_in, device=device) * 0.01)
        # B: Zero initialization (out_features x rank) - ensures initial output is same as base model
        self.lora_B = torch.nn.Parameter(torch.zeros(d_out, rank, device=device))

        self.scale = alpha / rank

    def forward(self, x):
        """Forward pass combining base model and LoRA adaptation.

        Args:
            x: Input tensor

        Returns:
            Output tensor with same shape as original linear layer output
        """
        base = self.orig(x)
        # LoRA branch: x @ A^T @ B^T * scale
        lora = (x @ self.lora_A.T) @ self.lora_B.T * self.scale
        return base + lora

    def extra_repr(self):
        """String representation for debugging."""
        return f"in_features={self.orig.in_features}, out_features={self.orig.out_features}, rank={self.lora_A.shape[0]}, scale={self.scale:.4f}"


def inject_lora(model, rank: int = 16, alpha: int = 32, target_names=("c_attn",)):
    """Replace matching Linear layers with LoRA wrappers.

    Args:
        model: PyTorch model to inject LoRA into
        rank: LoRA rank for all injected layers
        alpha: LoRA scaling factor
        target_names: Tuple of substring patterns to match layer names.
                     A layer is replaced if its name contains ANY of these patterns.

    Returns:
        List of LoRA parameters (lora_A and lora_B for each replaced layer)

    Example:
        >>> target_names = ("c_attn", "c_proj", "mlp")
        >>> lora_params = inject_lora(model, rank=64, alpha=32, target_names=target_names)
        >>> print(f"Injected {len(lora_params)//2} LoRA layers")
    """
    lora_params = []
    replaced_layers = set()

    for name, module in list(model.named_modules()):
        # A layer name can match multiple target substrings; inject only once
        if name in replaced_layers:
            continue

        for tgt in target_names:
            if tgt in name and isinstance(module, torch.nn.Linear):
                # Get parent module
                parent_name, child_name = name.rsplit(".", 1) if "." in name else ("", name)
                parent = model if parent_name == "" else dict(model.named_modules())[parent_name]

                # Replace with LoRA wrapper
                new_mod = LoRALinear(module, rank=rank, alpha=alpha)
                setattr(parent, child_name, new_mod)

                # Collect trainable parameters
                lora_params.extend([new_mod.lora_A, new_mod.lora_B])
                replaced_layers.add(name)
                break  # Stop checking other targets for this layer

    return lora_params


def merge_lora_state_dict(model):
    """Return a standard state_dict with LoRA weights merged into original weights.

    This function merges the LoRA adaptations back into the base model weights,
    producing a state dict that can be loaded without the LoRA wrapper.

    Args:
        model: Model with LoRALinear layers

    Returns:
        State dict with merged weights (suitable for standard torch.load)

    Note:
        The returned state dict does NOT include LoRA-specific keys (lora_A, lora_B, orig),
        making it compatible with the original model architecture.
    """
    merged = {}

    # Merge LoRA weights into base weights
    for name, module in model.named_modules():
        if isinstance(module, LoRALinear):
            # Compute merged weight: W_merged = W_base + (B @ A) * scale
            w = module.orig.weight + (module.lora_B @ module.lora_A) * module.scale
            base_key = name + ".weight"
            merged[base_key] = w.detach().cpu()

            # Handle bias if present
            if module.orig.bias is not None:
                merged[name + ".bias"] = module.orig.bias.detach().cpu()

    # Copy other parameters (non-LoRA layers)
    raw = model.state_dict()
    for k, v in raw.items():
        # Skip LoRA-specific keys
        skip = False
        for lora_key in (".lora_A", ".lora_B", ".orig.weight", ".orig.bias"):
            if lora_key in k:
                skip = True
                break
        if not skip and k not in merged:
            merged[k] = v.detach().cpu()

    return merged


def count_lora_params(model) -> tuple:
    """Count LoRA and total parameters in a model.

    Args:
        model: Model to analyze

    Returns:
        Tuple of (trainable_params, total_params)
    """
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    return trainable, total


def print_lora_info(model, verbose: bool = False):
    """Print LoRA injection statistics.

    Args:
        model: Model with LoRA layers
        verbose: If True, print details of each LoRA layer
    """
    lora_count = 0
    for name, module in model.named_modules():
        if isinstance(module, LoRALinear):
            lora_count += 1
            if verbose:
                print(f"  [LoRA] {name}: {module.extra_repr()}")

    trainable, total = count_lora_params(model)
    print(f"LoRA Info: {lora_count} layers | Trainable: {trainable:,} / {total:,} params ({100*trainable/total:.2f}%)")
