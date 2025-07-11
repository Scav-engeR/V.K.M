# Install VKM
sudo ./KSetup.sh

# Interactive mode
sudo vkm interactive

# Quick operations
vkm info                    # System information
vkm list-kernels           # Available kernels
sudo vkm switch 5.15.0     # Switch kernel
sudo vkm compile --optimization vps  # Compile optimized kernel
sudo vkm optimize          # Apply VPS optimizations
sudo vkm patch             # Download XanMod patches
sudo vkm harden           # Security hardening
vkm benchmark             # Performance testing
