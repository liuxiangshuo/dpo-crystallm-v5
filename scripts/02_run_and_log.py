from src.utils import make_run_dir, save_json, env_info
import torch

def main():
    run_dir = make_run_dir(outputs_dir="outputs", tag="smoke")
    save_json(env_info(), run_dir / "env.json")

    x = torch.randn(2000, 2000, device="cuda")
    y = x @ x
    result = {
        "y_mean": float(y.mean().item()),
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "torch_version": torch.__version__,
    }
    save_json(result, run_dir / "result.json")
    print("Saved to:", run_dir)

if __name__ == "__main__":
    main()
