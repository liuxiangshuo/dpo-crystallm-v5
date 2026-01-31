import sys

print("Python:", sys.version)
print("sys.executable:", sys.executable)

try:
    import torch
    print("torch:", torch.__version__)
    print("CUDA available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU name:", torch.cuda.get_device_name(0))
except Exception as e:
    print("Torch check failed:", repr(e))
