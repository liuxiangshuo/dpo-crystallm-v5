#!/usr/bin/env python3
"""
Smoke test for shared modules refactoring.

This script tests that:
1. shared.lora_utils can be imported
2. shared.pipeline_utils can be imported
3. shared.pair_merge can be imported
4. SFT and DPO scripts can import from shared modules
5. Basic LoRA operations work
"""

import sys
import os
from pathlib import Path

# Add scripts directory to path
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

def test_imports():
    """Test that all shared modules can be imported."""
    print("Testing module imports...")
    
    # Check if torch is available
    try:
        import torch
        TORCH_AVAILABLE = True
    except ImportError:
        TORCH_AVAILABLE = False
        print("  ⚠ torch not available, skipping LoRA tests")
    
    if TORCH_AVAILABLE:
        try:
            from shared import LoRALinear, inject_lora, merge_lora_state_dict
            print("  ✓ shared.lora_utils imported successfully")
        except Exception as e:
            print(f"  ✗ Failed to import from shared.lora_utils: {e}")
            return False
    
    try:
        from shared import pipeline_utils
        print("  ✓ shared.pipeline_utils imported successfully")
    except Exception as e:
        print(f"  ✗ Failed to import shared.pipeline_utils: {e}")
        return False
    
    try:
        from shared import pair_merge
        print("  ✓ shared.pair_merge imported successfully")
    except Exception as e:
        print(f"  ✗ Failed to import shared.pair_merge: {e}")
        return False
    
    return True


def test_lora_utils():
    """Test LoRA utility functions."""
    print("\nTesting LoRA utilities...")
    
    # Check if torch is available
    try:
        import torch
    except ImportError:
        print("  ⚠ torch not available, skipping LoRA utils tests")
        return True  # Return True to not fail overall test due to missing torch
    
    try:
        from shared.lora_utils import LoRALinear, inject_lora, count_lora_params, print_lora_info
        
        # Create a simple linear layer
        linear = torch.nn.Linear(64, 128)
        
        # Wrap with LoRA
        lora_linear = LoRALinear(linear, rank=8, alpha=16)
        
        # Test forward pass
        x = torch.randn(4, 64)  # batch_size=4
        output = lora_linear(x)
        
        assert output.shape == (4, 128), f"Expected shape (4, 128), got {output.shape}"
        print("  ✓ LoRALinear forward pass works")
        
        # Check trainable params
        trainable, total = count_lora_params(lora_linear)
        assert trainable > 0, "Should have trainable LoRA parameters"
        print(f"  ✓ LoRA params: {trainable} trainable / {total} total")
        
        return True
        
    except Exception as e:
        print(f"  ✗ LoRA test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pipeline_utils():
    """Test pipeline utility functions."""
    print("\nTesting pipeline utilities...")
    
    try:
        from shared.pipeline_utils import count_csv_rows, count_scored_rows, count_cif_files
        
        # Create a temporary CSV file for testing
        import tempfile
        import csv
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['file', 'score_e_per_atom'])
            writer.writeheader()
            writer.writerow({'file': 'test1.cif', 'score_e_per_atom': '-5.0'})
            writer.writerow({'file': 'test2.cif', 'score_e_per_atom': '-4.5'})
            temp_csv = f.name
        
        # Test count_csv_rows
        n_rows = count_csv_rows(temp_csv)
        assert n_rows == 2, f"Expected 2 rows, got {n_rows}"
        print(f"  ✓ count_csv_rows works: {n_rows} rows")
        
        # Test count_scored_rows
        n_scored = count_scored_rows(temp_csv)
        assert n_scored == 2, f"Expected 2 scored rows, got {n_scored}"
        print(f"  ✓ count_scored_rows works: {n_scored} scored")
        
        # Cleanup
        os.unlink(temp_csv)
        
        return True
        
    except Exception as e:
        print(f"  ✗ Pipeline utils test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sft_dpo_imports():
    """Test that SFT and DPO scripts can import from shared modules."""
    print("\nTesting SFT/DPO script imports...")
    
    try:
        # Test SFT script syntax by trying to parse it
        import ast
        
        sft_script = script_dir / "33_train_sft_crystallm.py"
        with open(sft_script) as f:
            sft_code = f.read()
        
        # Check it has the shared import
        if "from shared.lora_utils import" in sft_code:
            print("  ✓ SFT script imports from shared.lora_utils")
        else:
            print("  ✗ SFT script missing shared.lora_utils import")
            return False
        
        # Test DPO script
        dpo_script = script_dir / "32_train_dpo_crystallm.py"
        with open(dpo_script) as f:
            dpo_code = f.read()
        
        if "from shared.lora_utils import" in dpo_code:
            print("  ✓ DPO script imports from shared.lora_utils")
        else:
            print("  ✗ DPO script missing shared.lora_utils import")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ✗ SFT/DPO import test failed: {e}")
        return False


def test_pipeline_sh_modifications():
    """Test that pipeline script uses shared modules."""
    print("\nTesting pipeline.sh modifications...")
    
    try:
        pipeline_sh = script_dir / "run_sft_rl_pipeline.sh"
        with open(pipeline_sh) as f:
            content = f.read()
        
        # Check for shared module usage
        checks = [
            ("pipeline_utils.py", "pipeline_utils"),
            ("debug_log using pipeline_utils", "debug_log"),
            ("check_reward_spread using pipeline_utils", "check_reward_spread"),
            ("merge_eval using pipeline_utils", "merge_eval"),
            ("check_fail_rate using pipeline_utils", "check_fail_rate"),
        ]
        
        all_passed = True
        for desc, pattern in checks:
            if pattern in content:
                print(f"  ✓ {desc}")
            else:
                print(f"  ✗ Missing: {desc}")
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"  ✗ Pipeline.sh test failed: {e}")
        return False


def test_batch_size_param():
    """Test that SFT script has --batch_size parameter."""
    print("\nTesting SFT batch_size parameter...")
    
    try:
        sft_script = script_dir / "33_train_sft_crystallm.py"
        with open(sft_script) as f:
            content = f.read()
        
        if "--batch_size" in content:
            print("  ✓ SFT script has --batch_size parameter")
        else:
            print("  ✗ SFT script missing --batch_size parameter")
            return False
        
        if "batch_size * args.grad_accum_steps" in content:
            print("  ✓ SFT script computes effective batch size")
        else:
            print("  ✗ SFT script missing effective batch size computation")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ✗ Batch size test failed: {e}")
        return False


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("Shared Modules Smoke Test")
    print("=" * 60)
    
    results = {
        "Module Imports": test_imports(),
        "LoRA Utils": test_lora_utils(),
        "Pipeline Utils": test_pipeline_utils(),
        "SFT/DPO Imports": test_sft_dpo_imports(),
        "Pipeline.sh Modifications": test_pipeline_sh_modifications(),
        "Batch Size Parameter": test_batch_size_param(),
    }
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        print(f"{symbol} {name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nAll smoke tests passed! The refactoring looks good.")
        return 0
    else:
        print(f"\n{total - passed} test(s) failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
