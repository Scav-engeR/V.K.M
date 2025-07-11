# V.K.M
V.K.M - Virtual | Kernel | Manager -
# VPS Kernel Manager (VKM) v1.0

Advanced Linux Kernel Management Tool for Debian 10 (Buster) and Compatible Systems

## 🚀 Features

### Core Functionality
- **Interactive CLI Interface** - Rich, user-friendly terminal interface
- **Kernel Switching** - Seamless switching between installed kernels
- **Automated Compilation** - Custom kernel compilation with VPS optimizations
- **Patch Management** - Download and apply performance/security patches
- **VPS Optimizations** - Network, memory, and I/O optimizations
- **Security Hardening** - Kernel security configurations and audit logging
- **Performance Benchmarking** - System performance analysis and validation

### Advanced Features
- **Multiple Kernel Variants** - Support for XanMod, Liquorix, RT kernels
- **Automated Patching** - XanMod performance patches, security updates
- **BBR TCP Congestion Control** - Network performance optimization
- **Transparent Huge Pages** - Memory management optimization
- **I/O Scheduler Selection** - Optimized disk performance
- **Audit Logging** - Security compliance and monitoring
- **Configuration Management** - Flexible, persistent configuration system

## 📋 Prerequisites

### System Requirements
- **OS**: Debian 10 (Buster) or compatible (Ubuntu 18.04+)
- **Architecture**: x86_64 (amd64)
- **Memory**: 1GB+ RAM (2GB+ recommended for compilation)
- **Storage**: 2GB+ free space
- **Root Access**: Required for system operations

### Dependencies (Auto-installed)
- Python 3.6+
- Build tools (gcc, make, etc.)
- Kernel build dependencies
- Rich CLI library
- Click framework

## 🔧 Installation

### Quick Install
```bash
# Download the installer
wget https://raw.githubusercontent.com/your-repo/vkm/main/install.sh

# Make executable and run
chmod +x install.sh
sudo ./install.sh
```

### Manual Install
```bash
# Clone repository
git clone https://github.com/your-repo/vkm.git
cd vkm

# Run installer
sudo ./install.sh
```

### Verification
```bash
# Check installation
vkm --version
vkm info
```

## 🎮 Usage

### Interactive Mode (Recommended)
```bash
# Start interactive interface
sudo vkm interactive
```

The interactive mode provides a menu-driven interface with:
- System information display
- Kernel management options
- Real-time progress indicators
- Configuration management
- Help and guidance

### Command Line Interface

#### System Information
```bash
# Show system details
vkm info

# List available kernels
vkm list-kernels
```

#### Kernel Management
```bash
# Switch to specific kernel
sudo vkm switch 5.4.0-74-generic

# Compile custom kernel
sudo vkm compile --version latest --optimization vps

# Compile with specific options
sudo vkm compile --version 5.15.0 --optimization performance
```

#### Optimization
```bash
# Apply all VPS optimizations
sudo vkm optimize

# Apply specific optimizations
sudo vkm optimize --type network
sudo vkm optimize --type memory
sudo vkm optimize --type io
```

#### Patch Management
```bash
# Download XanMod performance patches
sudo vkm patch

# Download custom patch
sudo vkm patch --url https://example.com/patch.patch --name custom-patch
```

#### Security
```bash
# Apply security hardening
sudo vkm harden
```

#### Benchmarking
```bash
# Run performance benchmark
vkm benchmark
```

## ⚙️ Configuration

### Configuration File
Location: `/etc/vkm/vkm.conf` or `~/.vkm/config.ini`

```ini
[general]
build_dir = /tmp/vkm-build
kernel_source_dir = /usr/src
default_optimization = O2
parallel_jobs = 4
auto_backup = true
max_kernels = 5

[compilation]
compiler = gcc
enable_lto = false
enable_pgo = false
custom_cflags = -march=native
debug_info = false

[vps]
tcp_congestion = bbr
io_scheduler = mq-deadline
transparent_hugepages = madvise
vm_swappiness = 1
enable_thp = true

[security]
enable_hardening = true
secure_boot = false
sign_modules = false
audit_logging = true

[patches]
auto_download = true
patch_sources = https://github.com/xanmod/linux-patches
security_patches = true
performance_patches = true
```

### Kernel Optimization Levels

#### VPS (Default)
- Virtualization support optimized
- BBR TCP congestion control
- mq-deadline I/O scheduler
- Memory management for VPS
- Security hardening enabled

#### Performance
- Preemptible kernel (PREEMPT)
- 1000Hz timer frequency
- Aggressive CPU optimizations
- Minimal debugging

#### Minimal
- Monolithic kernel (no modules)
- Minimal feature set
- Optimized for size
- Fastest boot time

## 🔍 Advanced Usage

### Custom Kernel Compilation

#### Optimization Flags
```bash
# VPS-optimized build
sudo vkm compile --optimization vps

# Performance-focused build
sudo vkm compile --optimization performance

# Minimal build for containers
sudo vkm compile --optimization minimal
```

#### Custom Configuration
```bash
# Use specific compiler
vkm config set compilation compiler clang

# Enable Link Time Optimization
vkm config set compilation enable_lto true

# Custom CFLAGS
vkm config set compilation custom_cflags "-march=native -O3"
```

### Patch Management

#### XanMod Patches
- **BBRv3**: Latest TCP congestion control
- **CACULE Scheduler**: Interactive task scheduling
- **Multigenerational LRU**: Advanced memory management
- **LE9 Patches**: Low latency optimizations

#### Security Patches
- Automatic CVE patch detection
- Kernel hardening patches
- Security backports

#### Custom Patches
```bash
# Apply custom patch to kernel source
sudo vkm patch --url https://lkml.org/patch.mbox --name security-fix

# Apply patch during compilation
sudo vkm compile --patches custom-patch.patch
```

### VPS Optimizations

#### Network Optimization
- BBR/BBRv3 TCP congestion control
- Increased network buffers
- TCP window scaling
- Fast open connections

#### Memory Optimization
- Low swappiness (vm.swappiness=1)
- Optimized cache pressure
- Transparent huge pages
- Dirty page write optimization

#### I/O Optimization
- mq-deadline scheduler for SSDs
- BFQ scheduler for HDDs
- Optimized queue depths
- Read-ahead optimization

### Security Hardening

#### Kernel Security
- Address space layout randomization
- Stack protection
- Hardened user copy
- Restricted dmesg access

#### Audit Logging
- Kernel module monitoring
- System call auditing
- File access monitoring
- Security event logging

## 📊 Performance Benchmarking

### Network Benchmarks
- TCP throughput testing
- Latency measurements
- Congestion control validation
- Multi-connection testing

### Disk Benchmarks
- Sequential read/write speeds
- Random I/O performance
- I/O scheduler comparison
- Latency analysis

### Memory Benchmarks
- Memory bandwidth testing
- Cache performance
- THP effectiveness
- Swap usage analysis

## 🛠️ Troubleshooting

### Common Issues

#### Compilation Failures
```bash
# Check build dependencies
sudo apt install build-essential linux-source

# Verify disk space
df -h /tmp

# Check memory availability
free -h
```

#### Boot Issues
```bash
# Access GRUB menu during boot
# Select "Advanced options"
# Choose previous kernel

# Or use recovery mode
# Mount filesystem read-write
# Edit /etc/default/grub
# Run update-grub
```

#### Performance Issues
```bash
# Verify optimizations are applied
vkm benchmark

# Check sysctl settings
sysctl net.ipv4.tcp_congestion_control
sysctl vm.swappiness

# Monitor system performance
htop
iotop
```

### Logs and Debugging
```bash
# VKM logs
tail -f /var/log/vkm/vkm_$(date +%Y%m%d).log

# Kernel logs
dmesg | tail -50

# System logs
journalctl -f

# Compilation logs
tail -f /tmp/vkm-build/build.log
```

## 🔒 Security Considerations

### Kernel Security
- Only use trusted patch sources
- Verify signatures when possible
- Test kernels in non-production first
- Maintain kernel backups

### System Security
- Regular security updates
- Monitor audit logs
- Use secure boot when possible
- Keep build environment isolated

## 📈 Performance Tuning

### Network Performance
```bash
# Optimize for high bandwidth
echo 'net.core.rmem_max = 268435456' >> /etc/sysctl.conf
echo 'net.core.wmem_max = 268435456' >> /etc/sysctl.conf

# Enable BBR
echo 'net.ipv4.tcp_congestion_control = bbr' >> /etc/sysctl.conf

# Apply changes
sysctl -p
```

### Memory Performance
```bash
# Optimize for VPS
echo 'vm.swappiness = 1' >> /etc/sysctl.conf
echo 'vm.vfs_cache_pressure = 10' >> /etc/sysctl.conf

# Configure THP
echo madvise > /sys/kernel/mm/transparent_hugepage/enabled
```

### I/O Performance
```bash
# Set optimal I/O scheduler
echo mq-deadline > /sys/block/sda/queue/scheduler

# Optimize queue depth
echo 32 > /sys/block/sda/queue/nr_requests
```

## 🔄 Maintenance

### Regular Tasks
- Monitor kernel security advisories
- Update patches monthly
- Benchmark performance quarterly
- Review audit logs weekly

### Automated Maintenance
```bash
# Enable automatic monitoring
sudo systemctl enable vkm-monitor.timer

# Schedule weekly optimization checks
sudo crontab -e
# Add: 0 2 * * 1 /usr/local/bin/vkm optimize --auto
```

## 🆘 Support and Contributing

### Getting Help
- Check logs: `/var/log/vkm/`
- Run diagnostics: `vkm info`
- Review configuration: `vkm config show`

### Reporting Issues
Include:
- VKM version: `vkm --version`
- System info: `vkm info`
- Error logs: `/var/log/vkm/`
- Steps to reproduce

### Contributing
- Fork the repository
- Create feature branch
- Add tests for new features
- Submit pull request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

This tool modifies kernel configurations and system settings. While designed for safety:
- Always test in non-production environments first
- Maintain current kernel backups
- Understand the implications of changes
- Use at your own risk

VKM is not affiliated with any kernel maintainers or distributions.

## 🔗 References

- [Linux Kernel Documentation](https://www.kernel.org/doc/)
- [XanMod Kernel](https://xanmod.org/)
- [BBR Congestion Control](https://github.com/google/bbr)
- [Debian Kernel Handbook](https://kernel-team.pages.debian.net/kernel-handbook/)
- [VPS Optimization Guide](https://wiki.archlinux.org/title/Improving_performance)
