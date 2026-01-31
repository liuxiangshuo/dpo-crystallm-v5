import torch

# Make a big matrix on GPU and do a multiply
x = torch.randn(2000, 2000, device="cuda")
y = x @ x

print("OK, matmul done.")
print("y mean =", y.mean().item())
