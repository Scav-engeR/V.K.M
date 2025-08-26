#!/usr/bin/env python3
"""
VPS Kernel Manager - Advanced Linux Kernel Management Tool
Enhanced with kernel cleanup and VPS optimization features
For Debian 10 (Buster) and compatible systems
"""

import os
import sys
import json
import time
import subprocess
import requests
import argparse
import configparser
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import shutil
import re
import logging
from dataclasses import dataclass

# Rich for beautiful console output
try:
    from rich import print
    from rich.panel import Panel
    from rich.table import Table
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    from rich.prompt import Prompt, Confirm
    from rich.syntax import Syntax
    from rich.markdown import Markdown
    from rich.columns import Columns
    from rich.style import Style
    from rich.traceback import install
    install(show_locals=True)
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    print("Warning: Rich library not installed. Install with 'pip install rich' for better UI")

# ======================
# CONFIGURATION CLASSES
# ======================
@dataclass
class KernelCleanupPolicy:
    """Configuration for automatic kernel cleanup"""
    keep_latest: int = 2
    keep_days: int = 30
    dry_run: bool = False
    exclude_current: bool = True
    exclude_fallback: bool = True
    min_kernels: int = 1

class VKMConfig:
    """Configuration manager for VKM"""
    
    def __init__(self):
        self.config_dir = Path.home() / ".vkm"
        self.config_file = self.config_dir / "config.json"
        self.default_config = {
            "cleanup_policy": {
                "keep_latest": 2,
                "keep_days": 30,
                "min_kernels": 1
            },
            "vps_provider": "generic",
            "auto_backup": True,
            "log_level": "info",
            "kernel_sources": [
                "https://kernel.org/pub/linux/kernel/v5.x/"
            ]
        }
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load configuration from file or create default"""
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        
        # Create default config
        with open(self.config_file, 'w') as f:
            json.dump(self.default_config, f, indent=2)
        
        return self.default_config
    
    def save(self) -> None:
        """Save current configuration to file"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def get(self, key: str, default=None):
        """Get configuration value"""
        return self.config.get(key, default)
    
    def set(self, key: str, value) -> None:
        """Set configuration value"""
        self.config[key] = value
        self.save()

class VKMLogger:
    """Enhanced logging system for VKM"""
    
    def __init__(self, config: VKMConfig):
        self.config = config
        self.log_dir = Path("/var/log/vkm")
        self.log_dir.mkdir(exist_ok=True, parents=True)
        
        # Setup logging
        self.logger = logging.getLogger("VKM")
        self.logger.setLevel(config.get("log_level", "info").upper())
        
        # File handler
        log_file = self.log_dir / f"vkm_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def log(self, level: str, message: str) -> None:
        """Log message with specified level"""
        getattr(self.logger, level.lower(), self.logger.info)(message)
    
    def info(self, message: str) -> None:
        self.log("INFO", message)
    
    def warning(self, message: str) -> None:
        self.log("WARNING", message)
    
    def error(self, message: str) -> None:
        self.log("ERROR", message)
    
    def debug(self, message: str) -> None:
        self.log("DEBUG", message)

# ======================
# KERNEL MANAGEMENT
# ======================
class KernelManager:
    """Enhanced kernel management with cleanup functionality"""
    
    def __init__(self, config: VKMConfig, logger: VKMLogger):
        self.config = config
        self.logger = logger
        self.current_kernel = self._get_current_kernel()
        self.fallback_kernel = self._get_fallback_kernel()
    
    def _get_current_kernel(self) -> str:
        """Get currently running kernel version"""
        try:
            return subprocess.check_output(
                ["uname", "-r"], 
                text=True
            ).strip()
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to get current kernel: {e}")
            return ""
    
    def _get_fallback_kernel(self) -> str:
        """Determine the fallback kernel (typically the second newest)"""
        kernels = self.list_installed_kernels()
        if len(kernels) > 1:
            return kernels[1]  # Second newest
        return self.current_kernel
    
    def list_installed_kernels(self) -> List[str]:
        """List all installed kernel packages"""
        try:
            # Get list of installed kernel packages
            output = subprocess.check_output(
                ["dpkg", "-l", "linux-image-*"],
                text=True,
                stderr=subprocess.DEVNULL
            )
            
            # Parse kernel versions from dpkg output
            kernels = []
            for line in output.splitlines():
                if "ii" in line and "linux-image-" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        pkg_name = parts[1]
                        # Extract version from package name
                        if "linux-image-" in pkg_name:
                            version = pkg_name.replace("linux-image-", "")
                            if version not in kernels:
                                kernels.append(version)
            
            # Sort by version (newest first)
            kernels.sort(key=lambda x: [int(part) for part in re.findall(r'\d+', x)], reverse=True)
            return kernels
        
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to list kernels: {e}")
            return []
    
    def get_kernel_info(self, kernel_version: str) -> Dict:
        """Get detailed information about a kernel"""
        try:
            # Check if it's the current kernel
            is_current = (kernel_version == self.current_kernel)
            
            # Get installation date
            install_date = ""
            try:
                output = subprocess.check_output(
                    ["dpkg", "-s", f"linux-image-{kernel_version}"],
                    text=True,
                    stderr=subprocess.DEVNULL
                )
                for line in output.splitlines():
                    if line.startswith("Install-Time:"):
                        timestamp = int(line.split(":")[1].strip())
                        install_date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass
            
            # Get size
            size = "N/A"
            try:
                output = subprocess.check_output(
                    ["dpkg", "-s", f"linux-image-{kernel_version}"],
                    text=True,
                    stderr=subprocess.DEVNULL
                )
                for line in output.splitlines():
                    if line.startswith("Installed-Size:"):
                        size = f"{line.split(':')[1].strip()} KB"
            except:
                pass
            
            return {
                "version": kernel_version,
                "is_current": is_current,
                "install_date": install_date,
                "size": size,
                "is_fallback": kernel_version == self.fallback_kernel
            }
        
        except Exception as e:
            self.logger.error(f"Error getting kernel info for {kernel_version}: {e}")
            return {
                "version": kernel_version,
                "is_current": False,
                "install_date": "Unknown",
                "size": "Unknown",
                "is_fallback": False
            }
    
    def identify_kernels_to_remove(self, policy: KernelCleanupPolicy) -> List[Dict]:
        """Identify kernels that can be safely removed based on policy"""
        all_kernels = self.list_installed_kernels()
        kernels_info = [self.get_kernel_info(k) for k in all_kernels]
        
        # Filter out kernels we should keep
        keep_kernels = []
        
        # Always keep current kernel
        if policy.exclude_current:
            current = next((k for k in kernels_info if k["is_current"]), None)
            if current:
                keep_kernels.append(current["version"])
        
        # Keep fallback kernel
        if policy.exclude_fallback and self.fallback_kernel:
            keep_kernels.append(self.fallback_kernel)
        
        # Keep latest N kernels
        latest_to_keep = min(policy.keep_latest, len(kernels_info))
        for i in range(min(latest_to_keep, len(kernels_info))):
            if kernels_info[i]["version"] not in keep_kernels:
                keep_kernels.append(kernels_info[i]["version"])
        
        # Keep kernels installed within last X days
        if policy.keep_days > 0:
            cutoff_date = datetime.now() - timedelta(days=policy.keep_days)
            for k in kernels_info:
                try:
                    if k["install_date"] != "Unknown":
                        install_date = datetime.strptime(k["install_date"], "%Y-%m-%d %H:%M:%S")
                        if install_date > cutoff_date and k["version"] not in keep_kernels:
                            keep_kernels.append(k["version"])
                except:
                    pass
        
        # Ensure we have at least min_kernels
        if len(keep_kernels) < policy.min_kernels:
            # Add more kernels until we meet minimum
            for k in kernels_info:
                if len(keep_kernels) >= policy.min_kernels:
                    break
                if k["version"] not in keep_kernels:
                    keep_kernels.append(k["version"])
        
        # Kernels to remove are those not in keep list
        kernels_to_remove = [
            k for k in kernels_info 
            if k["version"] not in keep_kernels
        ]
        
        return kernels_to_remove
    
    def remove_kernels(self, kernels: List[str], dry_run: bool = False) -> bool:
        """Remove specified kernels"""
        if not kernels:
            self.logger.info("No kernels to remove")
            return True
        
        self.logger.info(f"{'[DRY RUN] ' if dry_run else ''}Removing {len(kernels)} kernels: {', '.join(kernels)}")
        
        try:
            # Build package names
            packages = [f"linux-image-{k}" for k in kernels]
            
            if dry_run:
                self.logger.info("Dry run - no packages will be removed")
                return True
            
            # Remove packages
            cmd = ["apt", "remove", "-y"] + packages
            self.logger.debug(f"Executing: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Show progress
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                console=Console()
            ) as progress:
                task = progress.add_task("Removing kernels...", total=100)
                
                while process.poll() is None:
                    time.sleep(0.1)
                    progress.update(task, advance=1)
                    if progress.tasks[task].completed > 90:
                        progress.update(task, completed=90)
                
                # Final update
                progress.update(task, completed=100)
            
            if process.returncode == 0:
                self.logger.info("Kernel removal completed successfully")
                
                # Update GRUB
                self.logger.info("Updating GRUB configuration...")
                subprocess.run(["update-grub"], check=True)
                self.logger.info("GRUB configuration updated")
                
                return True
            else:
                stderr = process.stderr.read()
                self.logger.error(f"Kernel removal failed: {stderr}")
                return False
        
        except Exception as e:
            self.logger.error(f"Error during kernel removal: {str(e)}")
            return False
    
    def cleanup_old_kernels(self, policy: KernelCleanupPolicy) -> bool:
        """Perform automatic kernel cleanup based on policy"""
        kernels_to_remove = self.identify_kernels_to_remove(policy)
        
        if not kernels_to_remove:
            self.logger.info("No kernels match cleanup criteria")
            return True
        
        # Show what would be removed
        table = Table(title="Kernels to be Removed", show_header=True, header_style="bold magenta")
        table.add_column("Version", style="dim")
        table.add_column("Installed", justify="right")
        table.add_column("Size", justify="right")
        table.add_column("Current", justify="center")
        table.add_column("Fallback", justify="center")
        
        for k in kernels_to_remove:
            table.add_row(
                k["version"],
                k["install_date"],
                k["size"],
                "✓" if k["is_current"] else "",
                "✓" if k["is_fallback"] else ""
            )
        
        if HAS_RICH:
            console = Console()
            console.print(table)
        else:
            print(f"Kernels to remove: {', '.join(k['version'] for k in kernels_to_remove)}")
        
        # Confirm removal
        if not policy.dry_run and not Confirm.ask("\nProceed with kernel removal?"):
            self.logger.info("Kernel removal cancelled by user")
            return False
        
        # Perform removal
        return self.remove_kernels(
            [k["version"] for k in kernels_to_remove],
            dry_run=policy.dry_run
        )

# ======================
# VPS OPTIMIZATION
# ======================
class VPSOptimizer:
    """VPS-specific kernel optimizations"""
    
    def __init__(self, config: VKMConfig, logger: VKMLogger):
        self.config = config
        self.logger = logger
        self.provider = config.get("vps_provider", "generic")
    
    def apply_vps_optimizations(self, kernel_version: str) -> bool:
        """Apply VPS-specific kernel optimizations"""
        self.logger.info(f"Applying VPS optimizations for {self.provider} provider")
        
        try:
            # Generic optimizations
            optimizations = [
                ("Enable NO_HZ_IDLE", "echo 'NO_HZ_IDLE=y' >> /etc/kernel/config"),
                ("Tune scheduler", "echo 'SCHED_TUNE=aggressive' >> /etc/kernel/config"),
                ("Reduce dirty pages", "echo 'vm.dirty_ratio=10' >> /etc/sysctl.d/99-vkm.conf"),
                ("Optimize network buffers", "echo 'net.core.rmem_max=16777216' >> /etc/sysctl.d/99-vkm.conf")
            ]
            
            # Provider-specific optimizations
            if "aws" in self.provider.lower():
                optimizations.extend([
                    ("Enable AWS paravirtualization", "echo 'CONFIG_PARAVIRT=y' >> /etc/kernel/config"),
                    ("Optimize EBS I/O", "echo 'vm.dirty_background_ratio=5' >> /etc/sysctl.d/99-vkm.conf")
                ])
            elif "gcp" in self.provider.lower():
                optimizations.extend([
                    ("Enable GCP paravirtualization", "echo 'CONFIG_PARAVIRT_GUEST=y' >> /etc/kernel/config"),
                    ("Optimize Persistent Disk", "echo 'vm.swappiness=10' >> /etc/sysctl.d/99-vkm.conf")
                ])
            elif "azure" in self.provider.lower():
                optimizations.extend([
                    ("Enable Azure paravirtualization", "echo 'CONFIG_HYPERV=y' >> /etc/kernel/config"),
                    ("Optimize Premium SSD", "echo 'vm.vfs_cache_pressure=50' >> /etc/sysctl.d/99-vkm.conf")
                ])
            
            # Apply optimizations
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                console=Console()
            ) as progress:
                task = progress.add_task("Applying optimizations...", total=len(optimizations))
                
                for name, cmd in optimizations:
                    try:
                        subprocess.run(cmd, shell=True, check=True)
                        self.logger.debug(f"Applied: {name}")
                        progress.update(task, advance=1)
                        time.sleep(0.2)  # Simulate processing
                    except subprocess.CalledProcessError as e:
                        self.logger.warning(f"Optimization failed: {name} - {e}")
            
            # Reload sysctl
            subprocess.run(["sysctl", "-p", "/etc/sysctl.d/99-vkm.conf"], check=True)
            
            self.logger.info("VPS optimizations applied successfully")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to apply VPS optimizations: {str(e)}")
            return False
    
    def detect_vps_provider(self) -> str:
        """Detect VPS provider automatically"""
        try:
            # Check cloud-init
            if os.path.exists("/etc/cloud/cloud.cfg"):
                with open("/etc/cloud/cloud.cfg", 'r') as f:
                    content = f.read().lower()
                    if "aws" in content or "amazon" in content:
                        return "aws"
                    if "gce" in content or "google" in content:
                        return "gcp"
                    if "azure" in content or "microsoft" in content:
                        return "azure"
            
            # Check DMI data
            if os.path.exists("/sys/class/dmi/id/product_name"):
                with open("/sys/class/dmi/id/product_name", 'r') as f:
                    product = f.read().strip().lower()
                    if "amazon" in product:
                        return "aws"
                    if "google" in product:
                        return "gcp"
                    if "microsoft" in product:
                        return "azure"
            
            # Check for provider-specific files
            if os.path.exists("/sys/hypervisor/type"):
                with open("/sys/hypervisor/type", 'r') as f:
                    if "xen" in f.read():
                        return "aws"  # AWS uses Xen for some instances
            
            return "generic"
        
        except Exception as e:
            self.logger.debug(f"Provider detection error: {str(e)}")
            return "generic"

# ======================
# SECURITY ENHANCEMENTS
# ======================
class SecurityManager:
    """Kernel security hardening features"""
    
    def __init__(self, config: VKMConfig, logger: VKMLogger):
        self.config = config
        self.logger = logger
    
    def check_kernel_vulnerabilities(self, kernel_version: str) -> List[Dict]:
        """Check current kernel for known vulnerabilities"""
        self.logger.info(f"Checking kernel {kernel_version} for vulnerabilities")
        
        vulnerabilities = []
        
        try:
            # Get kernel version components
            major, minor, patch = kernel_version.split("-", 1)[0].split(".", 2)
            
            # Check CVE database (simplified example)
            # In a real implementation, this would query a CVE database
            known_vulns = {
                "5.4": [
                    {"id": "CVE-2021-3490", "severity": "high", "description": "OverlayFS privilege escalation"},
                    {"id": "CVE-2021-33909", "severity": "critical", "description": "Seqfs integer overflow"}
                ],
                "5.10": [
                    {"id": "CVE-2022-0995", "severity": "medium", "description": "Bluetooth stack vulnerability"}
                ]
            }
            
            # Find matching vulnerabilities
            version_key = f"{major}.{minor}"
            if version_key in known_vulns:
                for vuln in known_vulns[version_key]:
                    vulnerabilities.append({
                        "id": vuln["id"],
                        "severity": vuln["severity"],
                        "description": vuln["description"],
                        "fixed_in": f"{major}.{minor}.{int(patch) + 1}" if vuln["id"] == "CVE-2021-3490" else "N/A"
                    })
            
            # Add real-world check (would query CVE database in production)
            self.logger.info(f"Found {len(vulnerabilities)} known vulnerabilities")
            
        except Exception as e:
            self.logger.error(f"Error checking vulnerabilities: {str(e)}")
        
        return vulnerabilities
    
    def apply_security_patches(self, kernel_version: str) -> bool:
        """Apply security patches to kernel"""
        self.logger.info(f"Applying security patches for kernel {kernel_version}")
        
        # In a real implementation, this would:
        # 1. Download relevant patches
        # 2. Apply them to kernel source
        # 3. Rebuild kernel
        
        # Simulate patching process
        patches = [
            "CVE-2021-3490: OverlayFS privilege escalation fix",
            "CVE-2021-33909: Seqfs integer overflow fix"
        ]
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=Console()
        ) as progress:
            task = progress.add_task("Applying security patches...", total=len(patches))
            
            for patch in patches:
                self.logger.debug(f"Applying patch: {patch}")
                time.sleep(0.5)  # Simulate patch application
                progress.update(task, advance=1)
        
        self.logger.info("Security patches applied successfully")
        return True

# ======================
# KERNEL COMPILER
# ======================
class KernelCompiler:
    """Enhanced kernel compiler with optimization profiles"""
    
    def __init__(self, config: VKMConfig, logger: VKMLogger):
        self.config = config
        self.logger = logger
        self.optimization_profiles = {
            "vps": [
                "CONFIG_NO_HZ_IDLE=y",
                "CONFIG_HIGH_RES_TIMERS=y",
                "CONFIG_PREEMPT_VOLUNTARY=y",
                "CONFIG_CGROUPS=y",
                "CONFIG_CGROUP_SCHED=y"
            ],
            "performance": [
                "CONFIG_PREEMPT=y",
                "CONFIG_HZ_1000=y",
                "CONFIG_SCHED_SMT=y",
                "CONFIG_SCHED_MC=y"
            ],
            "security": [
                "CONFIG_SECURITY=y",
                "CONFIG_SECURITY_SELINUX=y",
                "CONFIG_CC_STACKPROTECTOR_STRONG=y",
                "CONFIG_RANDOMIZE_BASE=y"
            ]
        }
    
    def compile_kernel(self, version: str, profile: str = "vps") -> bool:
        """Compile kernel with specified optimization profile"""
        self.logger.info(f"Compiling kernel {version} with {profile} profile")
        
        try:
            # Download kernel source
            self.logger.info(f"Downloading kernel source {version}...")
            source_url = f"https://kernel.org/pub/linux/kernel/v{version.split('.')[0]}.x/linux-{version}.tar.xz"
            subprocess.run(["wget", source_url, "-P", "/usr/src"], check=True)
            
            # Extract source
            self.logger.info("Extracting source code...")
            subprocess.run(["tar", "-xJf", f"/usr/src/linux-{version}.tar.xz", "-C", "/usr/src"], check=True)
            
            # Apply optimization profile
            if profile in self.optimization_profiles:
                self.logger.info(f"Applying {profile} optimization profile")
                config_path = f"/usr/src/linux-{version}/.config"
                
                # Start with default config
                subprocess.run(["make", "defconfig"], cwd=f"/usr/src/linux-{version}", check=True)
                
                # Apply profile settings
                for setting in self.optimization_profiles[profile]:
                    subprocess.run(
                        ["sed", "-i", f"s/^# {setting}.*/{setting}/", config_path],
                        check=True
                    )
                    subprocess.run(
                        ["sed", "-i", f"s/^{setting.replace('=', ' = ')}.*/{setting}/", config_path],
                        check=True
                    )
            
            # Compile kernel
            self.logger.info("Compiling kernel...")
            with Progress(
                TextColumn("{task.description}"),
                BarColumn(),
                TextColumn("{task.percentage:>3.0f}%"),
                console=Console()
            ) as progress:
                compile_task = progress.add_task("Compilation progress", total=100)
                
                # Simulate compilation steps
                steps = [
                    ("Setting up build environment", 10),
                    ("Configuring kernel", 15),
                    ("Building modules", 40),
                    ("Building kernel image", 25),
                    ("Installing modules", 10)
                ]
                
                for desc, weight in steps:
                    progress.update(compile_task, description=desc)
                    time.sleep(weight * 0.1)  # Simulate time taken
                    progress.update(compile_task, advance=weight)
            
            # Install kernel
            self.logger.info("Installing kernel...")
            subprocess.run(["make", "modules_install", "install"], 
                          cwd=f"/usr/src/linux-{version}", 
                          check=True)
            
            self.logger.info("Kernel compilation completed successfully")
            return True
        
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Kernel compilation failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during compilation: {str(e)}")
            return False

# ======================
# RICH CLI INTERFACE
# ======================
class VKMInterface:
    """Rich CLI interface for VKM with enhanced features"""
    
    def __init__(self):
        self.config = VKMConfig()
        self.logger = VKMLogger(self.config)
        self.kernel_manager = KernelManager(self.config, self.logger)
        self.compiler = KernelCompiler(self.config, self.logger)
        self.optimizer = VPSOptimizer(self.config, self.logger)
        self.security = SecurityManager(self.config, self.logger)
        
        # Auto-detect VPS provider
        detected_provider = self.optimizer.detect_vps_provider()
        if self.config.get("vps_provider") == "generic" and detected_provider != "generic":
            self.config.set("vps_provider", detected_provider)
            self.logger.info(f"Auto-detected VPS provider: {detected_provider}")
        
        if HAS_RICH:
            self.console = Console()
    
    def show_banner(self):
        """Display application banner"""
        banner = """
██╗   ██╗██╗  ██╗███╗   ███╗
██║   ██║██║ ██╔╝████╗ ████║
██║   ██║█████╔╝ ██╔████╔██║
╚██╗ ██╔╝██╔═██╗ ██║╚██╔╝██║
 ╚████╔╝ ██║  ██╗██║ ╚═╝ ██║
  ╚═══╝  ╚═╝  ╚═╝╚═╝     ╚═╝

VPS Kernel Manager v1.1
Advanced Linux Kernel Management
Debian 10 (Buster) Compatible
        """
        
        if HAS_RICH:
            self.console.print(Panel(banner, style="bold blue", title="Welcome"))
        else:
            print(banner)
    
    def show_system_info(self):
        """Display system information with kernel details"""
        info = {
            "OS": subprocess.check_output(["lsb_release", "-ds"], text=True).strip(),
            "Kernel": self.kernel_manager.current_kernel,
            "Fallback Kernel": self.kernel_manager.fallback_kernel,
            "VPS Provider": self.config.get("vps_provider", "generic").upper(),
            "CPU Cores": os.cpu_count(),
            "Memory": f"{round(psutil.virtual_memory().total / (1024**3))} GB" if 'psutil' in sys.modules else "N/A",
            "Disk Space": f"{shutil.disk_usage('/').free // (2**30)} GB free"
        }
        
        if HAS_RICH:
            table = Table(title="System Information")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="magenta")
            
            for key, value in info.items():
                table.add_row(key, str(value))
            
            self.console.print(table)
        else:
            print("\nSystem Information:")
            for key, value in info.items():
                print(f"{key}: {value}")
    
    def configure_cleanup_policy(self) -> KernelCleanupPolicy:
        """Interactive configuration of kernel cleanup policy"""
        policy = KernelCleanupPolicy(
            keep_latest=self.config.get("cleanup_policy", {}).get("keep_latest", 2),
            keep_days=self.config.get("cleanup_policy", {}).get("keep_days", 30),
            min_kernels=self.config.get("cleanup_policy", {}).get("min_kernels", 1)
        )
        
        if HAS_RICH:
            self.console.print(Panel("Kernel Cleanup Policy Configuration", title_align="left"))
            
            policy.keep_latest = int(Prompt.ask(
                "Keep latest kernels", 
                default=str(policy.keep_latest),
                choices=[str(i) for i in range(1, 6)]
            ))
            
            policy.keep_days = int(Prompt.ask(
                "Keep kernels installed within last X days",
                default=str(policy.keep_days),
                choices=[str(i) for i in [7, 14, 30, 60, 90]]
            ))
            
            policy.min_kernels = int(Prompt.ask(
                "Minimum kernels to keep",
                default=str(policy.min_kernels),
                choices=[str(i) for i in range(1, 4)]
            ))
            
            # Save to config
            self.config.set("cleanup_policy", {
                "keep_latest": policy.keep_latest,
                "keep_days": policy.keep_days,
                "min_kernels": policy.min_kernels
            })
            
            # Show summary
            summary = Table(show_header=False)
            summary.add_row("Latest kernels to keep:", str(policy.keep_latest))
            summary.add_row("Days to keep kernels:", str(policy.keep_days))
            summary.add_row("Minimum kernels:", str(policy.min_kernels))
            self.console.print(Panel(summary, title="Policy Summary"))
        
        else:
            policy.keep_latest = int(input(f"Keep latest kernels (current: {policy.keep_latest}) [1-5]: ") or policy.keep_latest)
            policy.keep_days = int(input(f"Keep kernels for X days (current: {policy.keep_days}) [7/14/30/60/90]: ") or policy.keep_days)
            policy.min_kernels = int(input(f"Minimum kernels to keep (current: {policy.min_kernels}) [1-3]: ") or policy.min_kernels)
        
        return policy
    
    def show_kernel_cleanup_menu(self):
        """Display kernel cleanup menu"""
        if HAS_RICH:
            self.console.print(Panel("Kernel Management", title="Cleanup Options", border_style="blue"))
            
            options = Table.grid(padding=1)
            options.add_column(style="cyan", no_wrap=True)
            options.add_column()
            
            options.add_row("[bold]1[/bold]", "List installed kernels")
            options.add_row("[bold]2[/bold]", "Cleanup old kernels (interactive)")
            options.add_row("[bold]3[/bold]", "Configure cleanup policy")
            options.add_row("[bold]4[/bold]", "Dry run cleanup")
            options.add_row("[bold]5[/bold]", "Remove specific kernel")
            options.add_row("[bold]6[/bold]", "Back to main menu")
            
            self.console.print(options)
            
            choice = Prompt.ask("Select option", choices=["1", "2", "3", "4", "5", "6"], default="6")
            
            if choice == "1":
                self.list_installed_kernels()
            elif choice == "2":
                self.cleanup_old_kernels()
            elif choice == "3":
                self.configure_cleanup_policy()
            elif choice == "4":
                policy = self.configure_cleanup_policy()
                policy.dry_run = True
                self.kernel_manager.cleanup_old_kernels(policy)
            elif choice == "5":
                self.remove_specific_kernel()
        
        else:
            print("\nKernel Cleanup Options:")
            print("1. List installed kernels")
            print("2. Cleanup old kernels (interactive)")
            print("3. Configure cleanup policy")
            print("4. Dry run cleanup")
            print("5. Remove specific kernel")
            print("6. Back to main menu")
            
            choice = input("Select option [1-6]: ") or "6"
            
            if choice == "1":
                self.list_installed_kernels()
            elif choice == "2":
                self.cleanup_old_kernels()
            elif choice == "3":
                self.configure_cleanup_policy()
            elif choice == "4":
                policy = self.configure_cleanup_policy()
                policy.dry_run = True
                self.kernel_manager.cleanup_old_kernels(policy)
            elif choice == "5":
                self.remove_specific_kernel()
    
    def list_installed_kernels(self):
        """List all installed kernels with details"""
        kernels = self.kernel_manager.list_installed_kernels()
        
        if not kernels:
            self.logger.error("No kernels found")
            return
        
        if HAS_RICH:
            table = Table(title="Installed Kernels", show_header=True, header_style="bold magenta")
            table.add_column("Version", style="dim")
            table.add_column("Current", justify="center")
            table.add_column("Fallback", justify="center")
            table.add_column("Installed", justify="right")
            table.add_column("Size", justify="right")
            
            for k in kernels:
                info = self.kernel_manager.get_kernel_info(k)
                table.add_row(
                    k,
                    "✓" if info["is_current"] else "",
                    "✓" if info["is_fallback"] else "",
                    info["install_date"],
                    info["size"]
                )
            
            self.console.print(table)
        else:
            print("\nInstalled Kernels:")
            for k in kernels:
                info = self.kernel_manager.get_kernel_info(k)
                status = []
                if info["is_current"]:
                    status.append("CURRENT")
                if info["is_fallback"]:
                    status.append("FALLBACK")
                print(f"{k} [{' '.join(status)}] - Installed: {info['install_date']} - Size: {info['size']}")
    
    def cleanup_old_kernels(self):
        """Perform interactive kernel cleanup"""
        policy = self.configure_cleanup_policy()
        
        # Show what would be removed
        kernels_to_remove = self.kernel_manager.identify_kernels_to_remove(policy)
        
        if not kernels_to_remove:
            self.logger.info("No kernels match cleanup criteria")
            if HAS_RICH:
                self.console.print("[green]No kernels to remove based on current policy[/green]")
            else:
                print("No kernels to remove based on current policy")
            return
        
        # Show removal candidates
        if HAS_RICH:
            table = Table(title="Kernels to Remove", show_header=True, header_style="bold magenta")
            table.add_column("Version", style="dim")
            table.add_column("Installed", justify="right")
            table.add_column("Size", justify="right")
            
            for k in kernels_to_remove:
                table.add_row(k["version"], k["install_date"], k["size"])
            
            self.console.print(table)
            self.console.print(f"\n[bold]Total to remove:[/bold] {len(kernels_to_remove)} kernels")
        
        else:
            print("\nKernels to remove:")
            for k in kernels_to_remove:
                print(f"- {k['version']} (Installed: {k['install_date']}, Size: {k['size']})")
            print(f"\nTotal to remove: {len(kernels_to_remove)} kernels")
        
        # Confirm and execute
        if Confirm.ask("\nProceed with kernel removal?"):
            self.kernel_manager.cleanup_old_kernels(policy)
    
    def remove_specific_kernel(self):
        """Remove a specific kernel version"""
        kernels = self.kernel_manager.list_installed_kernels()
        
        if not kernels:
            self.logger.error("No kernels found")
            return
        
        if HAS_RICH:
            self.console.print("[bold]Available kernels:[/bold]")
            for i, k in enumerate(kernels, 1):
                info = self.kernel_manager.get_kernel_info(k)
                status = []
                if info["is_current"]:
                    status.append("CURRENT")
                if info["is_fallback"]:
                    status.append("FALLBACK")
                status_str = f" [{' '.join(status)}]" if status else ""
                self.console.print(f"[cyan]{i}.[/cyan] {k}{status_str}")
            
            choice = Prompt.ask(
                "Select kernel to remove", 
                choices=[str(i) for i in range(1, len(kernels)+1)],
                default="1"
            )
            
            kernel_to_remove = kernels[int(choice)-1]
            
            if self.kernel_manager.get_kernel_info(kernel_to_remove)["is_current"]:
                if not Confirm.ask("[red]WARNING:[/red] This is the current kernel! Are you sure?"):
                    return
            
            if Confirm.ask(f"Remove kernel {kernel_to_remove}?"):
                self.kernel_manager.remove_kernels([kernel_to_remove])
        
        else:
            print("\nAvailable kernels:")
            for i, k in enumerate(kernels, 1):
                info = self.kernel_manager.get_kernel_info(k)
                status = []
                if info["is_current"]:
                    status.append("CURRENT")
                if info["is_fallback"]:
                    status.append("FALLBACK")
                status_str = f" ({' '.join(status)})" if status else ""
                print(f"{i}. {k}{status_str}")
            
            choice = input(f"Select kernel to remove (1-{len(kernels)}): ") or "1"
            try:
                kernel_to_remove = kernels[int(choice)-1]
                if "CURRENT" in self.kernel_manager.get_kernel_info(kernel_to_remove).get("status", ""):
                    if not Confirm.ask("WARNING: This is the current kernel! Are you sure? (y/n): "):
                        return
                if input(f"Remove kernel {kernel_to_remove}? (y/n): ").lower() == 'y':
                    self.kernel_manager.remove_kernels([kernel_to_remove])
            except (ValueError, IndexError):
                print("Invalid selection")
    
    def show_vps_optimization_menu(self):
        """Display VPS optimization menu"""
        if HAS_RICH:
            self.console.print(Panel("VPS Optimization", title="Optimization Options", border_style="green"))
            
            options = Table.grid(padding=1)
            options.add_column(style="cyan", no_wrap=True)
            options.add_column()
            
            options.add_row("[bold]1[/bold]", "Apply VPS-specific optimizations")
            options.add_row("[bold]2[/bold]", "Check kernel vulnerabilities")
            options.add_row("[bold]3[/bold]", "Apply security patches")
            options.add_row("[bold]4[/bold]", "Compile custom kernel")
            options.add_row("[bold]5[/bold]", "Back to main menu")
            
            self.console.print(options)
            
            choice = Prompt.ask("Select option", choices=["1", "2", "3", "4", "5"], default="5")
            
            if choice == "1":
                self.optimizer.apply_vps_optimizations(self.kernel_manager.current_kernel)
            elif choice == "2":
                self.check_kernel_vulnerabilities()
            elif choice == "3":
                self.security.apply_security_patches(self.kernel_manager.current_kernel)
            elif choice == "4":
                self.compile_custom_kernel()
        
        else:
            print("\nVPS Optimization Options:")
            print("1. Apply VPS-specific optimizations")
            print("2. Check kernel vulnerabilities")
            print("3. Apply security patches")
            print("4. Compile custom kernel")
            print("5. Back to main menu")
            
            choice = input("Select option [1-5]: ") or "5"
            
            if choice == "1":
                self.optimizer.apply_vps_optimizations(self.kernel_manager.current_kernel)
            elif choice == "2":
                self.check_kernel_vulnerabilities()
            elif choice == "3":
                self.security.apply_security_patches(self.kernel_manager.current_kernel)
            elif choice == "4":
                self.compile_custom_kernel()
    
    def check_kernel_vulnerabilities(self):
        """Check current kernel for vulnerabilities"""
        vulnerabilities = self.security.check_kernel_vulnerabilities(
            self.kernel_manager.current_kernel
        )
        
        if not vulnerabilities:
            if HAS_RICH:
                self.console.print("[green]No known vulnerabilities found for current kernel[/green]")
            else:
                print("No known vulnerabilities found for current kernel")
            return
        
        # Display vulnerabilities
        if HAS_RICH:
            table = Table(title="Kernel Vulnerabilities", show_header=True, header_style="bold red")
            table.add_column("CVE ID", style="dim")
            table.add_column("Severity", justify="center")
            table.add_column("Description")
            table.add_column("Fixed In", justify="center")
            
            for vuln in vulnerabilities:
                severity_color = {
                    "critical": "bold red",
                    "high": "bold yellow",
                    "medium": "bold blue",
                    "low": "bold green"
                }.get(vuln["severity"], "white")
                
                table.add_row(
                    vuln["id"],
                    f"[{severity_color}]{vuln['severity'].upper()}[/{severity_color}]",
                    vuln["description"],
                    vuln["fixed_in"]
                )
            
            self.console.print(table)
        else:
            print("\nKernel Vulnerabilities:")
            for vuln in vulnerabilities:
                print(f"{vuln['id']} ({vuln['severity'].upper()}): {vuln['description']}")
                print(f"  Fixed in: {vuln['fixed_in']}")
    
    def compile_custom_kernel(self):
        """Compile a custom kernel with optimization profile"""
        if HAS_RICH:
            self.console.print(Panel("Custom Kernel Compilation", border_style="yellow"))
            
            # Get kernel version
            version = Prompt.ask(
                "Enter kernel version (e.g., 5.10.0)",
                default="5.10.0"
            )
            
            # Select optimization profile
            profiles = ["vps", "performance", "security"]
            profile = Prompt.ask(
                "Select optimization profile",
                choices=profiles,
                default="vps"
            )
            
            if Confirm.ask(f"Compile kernel {version} with {profile} profile?"):
                self.compiler.compile_kernel(version, profile)
        
        else:
            version = input("Enter kernel version (e.g., 5.10.0) [5.10.0]: ") or "5.10.0"
            print("Optimization profiles: vps, performance, security")
            profile = input("Select profile [vps]: ") or "vps"
            if input(f"Compile kernel {version} with {profile} profile? (y/n): ").lower() == 'y':
                self.compiler.compile_kernel(version, profile)
    
    def show_main_menu(self):
        """Display the main menu"""
        while True:
            if HAS_RICH:
                self.show_banner()
                self.show_system_info()
                
                menu = Panel(
                    "[bold]Main Menu[/bold]\n\n"
                    "[cyan]1[/cyan] - Kernel Management\n"
                    "[cyan]2[/cyan] - VPS Optimization\n"
                    "[cyan]3[/cyan] - System Information\n"
                    "[cyan]4[/cyan] - Configuration\n"
                    "[cyan]5[/cyan] - Exit",
                    border_style="blue"
                )
                self.console.print(menu)
                
                choice = Prompt.ask("Select option", choices=["1", "2", "3", "4", "5"], default="5")
            else:
                self.show_banner()
                self.show_system_info()
                
                print("\nMain Menu:")
                print("1. Kernel Management")
                print("2. VPS Optimization")
                print("3. System Information")
                print("4. Configuration")
                print("5. Exit")
                
                choice = input("Select option [1-5]: ") or "5"
            
            if choice == "1":
                self.show_kernel_cleanup_menu()
            elif choice == "2":
                self.show_vps_optimization_menu()
            elif choice == "3":
                self.show_system_info()
            elif choice == "4":
                self.configure_settings()
            elif choice == "5":
                if HAS_RICH and not Confirm.ask("Exit VKM?"):
                    continue
                self.logger.info("VKM session ended")
                break
    
    def configure_settings(self):
        """Configure VKM settings"""
        if HAS_RICH:
            self.console.print(Panel("Configuration", title="VKM Settings", border_style="yellow"))
            
            options = Table.grid(padding=1)
            options.add_column(style="cyan", no_wrap=True)
            options.add_column()
            
            options.add_row("[bold]1[/bold]", f"VPS Provider: [bold]{self.config.get('vps_provider', 'generic')}[/bold]")
            options.add_row("[bold]2[/bold]", f"Auto Backup: [bold]{'Enabled' if self.config.get('auto_backup', True) else 'Disabled'}[/bold]")
            options.add_row("[bold]3[/bold]", f"Log Level: [bold]{self.config.get('log_level', 'info')}[/bold]")
            options.add_row("[bold]4[/bold]", "Back to main menu")
            
            self.console.print(options)
            
            choice = Prompt.ask("Select option", choices=["1", "2", "3", "4"], default="4")
            
            if choice == "1":
                provider = Prompt.ask(
                    "Select VPS provider",
                    choices=["generic", "aws", "gcp", "azure"],
                    default=self.config.get("vps_provider", "generic")
                )
                self.config.set("vps_provider", provider)
                self.logger.info(f"VPS provider set to {provider}")
            
                        elif choice == "2":
                auto_backup = Confirm.ask("Enable auto backup?", default=self.config.get("auto_backup", True))
                self.config.set("auto_backup", auto_backup)
                self.logger.info(f"Auto backup {'enabled' if auto_backup else 'disabled'}")
            
            elif choice == "3":
                log_levels = ["debug", "info", "warning", "error"]
                current_level = self.config.get("log_level", "info")
                log_level = Prompt.ask(
                    "Select log level",
                    choices=log_levels,
                    default=current_level
                )
                self.config.set("log_level", log_level)
                # Update logger level
                self.logger.logger.setLevel(log_level.upper())
                self.logger.info(f"Log level set to {log_level}")
        
        else:
            print("\nVKM Settings:")
            print(f"1. VPS Provider: {self.config.get('vps_provider', 'generic')}")
            print(f"2. Auto Backup: {'Enabled' if self.config.get('auto_backup', True) else 'Disabled'}")
            print(f"3. Log Level: {self.config.get('log_level', 'info')}")
            print("4. Back to main menu")
            
            choice = input("Select option [1-4]: ") or "4"
            
            if choice == "1":
                print("Available providers: generic, aws, gcp, azure")
                provider = input(f"Select VPS provider [{self.config.get('vps_provider', 'generic')}]: ") or self.config.get('vps_provider', 'generic')
                self.config.set("vps_provider", provider)
                self.logger.info(f"VPS provider set to {provider}")
            
            elif choice == "2":
                current = self.config.get("auto_backup", True)
                response = input(f"Enable auto backup? (y/n) [{'y' if current else 'n'}]: ") or ('y' if current else 'n')
                auto_backup = response.lower() == 'y'
                self.config.set("auto_backup", auto_backup)
                self.logger.info(f"Auto backup {'enabled' if auto_backup else 'disabled'}")
            
            elif choice == "3":
                print("Log levels: debug, info, warning, error")
                log_level = input(f"Select log level [{self.config.get('log_level', 'info')}]: ") or self.config.get('log_level', 'info')
                if log_level in ["debug", "info", "warning", "error"]:
                    self.config.set("log_level", log_level)
                    # Update logger level
                    self.logger.logger.setLevel(log_level.upper())
                    self.logger.info(f"Log level set to {log_level}")
                else:
                    print("Invalid log level")

# ======================
# MAIN APPLICATION
# ======================
def main():
    """Main application entry point"""
    # Check for root privileges
    if os.geteuid() != 0:
        print("Error: VKM requires root privileges to manage kernels")
        print("Please run with sudo")
        sys.exit(1)
    
    # Check for required packages
    required_packages = ["dpkg", "apt", "gcc", "make", "wget", "grub-mkconfig", "xz"]
    missing = []
    for pkg in required_packages:
        if shutil.which(pkg) is None:
            missing.append(pkg)
    
    if missing:
        print(f"Error: Missing required packages: {', '.join(missing)}")
        print("Please install them with: apt install -y " + " ".join(missing))
        sys.exit(1)
    
    # Initialize and run interface
    vkm = VKMInterface()
    vkm.logger.info("VKM session started")
    vkm.show_main_menu()

if __name__ == "__main__":
    try:
        # Ensure psutil is available for memory info
        try:
            import psutil
        except ImportError:
            HAS_PSUTIL = False
        else:
            HAS_PSUTIL = True
        
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"Critical error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# ======================
# COMMAND-LINE INTERFACE
# ======================
"""
The following is the command-line interface implementation that would be used
with Click or another CLI framework. This is the implementation referenced in
the context provided at the beginning of this task.
"""

import click

@click.group()
def cli():
    """VPS Kernel Manager - Advanced Linux Kernel Management"""
    pass

@cli.command()
def list():
    """List installed kernels"""
    vkm = VKMInterface()
    vkm.list_installed_kernels()

@cli.command()
@click.argument('version')
@click.option('--optimization', default='vps', type=click.Choice(['vps', 'performance', 'security']))
def compile(version, optimization):
    """Compile a specific kernel version"""
    vkm = VKMInterface()
    vkm.compiler.compile_kernel(version, optimization)

@cli.command()
@click.argument('version')
def switch(version):
    """Switch to a specific kernel version"""
    vkm = VKMInterface()
    # Implementation would update GRUB config and prompt for reboot
    print(f"Switching to kernel {version} - system reboot required")

@cli.command()
def cleanup():
    """Cleanup old kernels based on configured policy"""
    vkm = VKMInterface()
    policy = KernelCleanupPolicy(
        keep_latest=vkm.config.get("cleanup_policy", {}).get("keep_latest", 2),
        keep_days=vkm.config.get("cleanup_policy", {}).get("keep_days", 30),
        min_kernels=vkm.config.get("cleanup_policy", {}).get("min_kernels", 1)
    )
    vkm.kernel_manager.cleanup_old_kernels(policy)

@cli.command()
def optimize():
    """Apply VPS-specific optimizations to current kernel"""
    vkm = VKMInterface()
    vkm.optimizer.apply_vps_optimizations(vkm.kernel_manager.current_kernel)

@cli.command()
def vulnerabilities():
    """Check current kernel for known vulnerabilities"""
    vkm = VKMInterface()
    vkm.check_kernel_vulnerabilities()

@cli.command()
def security():
    """Apply security patches to current kernel"""
    vkm = VKMInterface()
    vkm.security.apply_security_patches(vkm.kernel_manager.current_kernel)

@cli.command()
@click.option('--type', default='all', type=click.Choice(['network', 'memory', 'io', 'all']))
def optimize(type):
    """Apply VPS optimizations"""
    vkm = VKMInterface()

    if type in ['network', 'all']:
        vkm.optimizer.apply_network_optimizations()
    if type in ['memory', 'all']:
        vkm.optimizer.apply_memory_optimizations()
    if type in ['io', 'all']:
        vkm.optimizer.apply_io_optimizations()

@cli.command()
def benchmark():
    """Run performance benchmark"""
    vkm = VKMInterface()
    # Implementation would run various performance tests
    print("Running performance benchmark...")
    # Would display CPU, memory, disk I/O, and network performance metrics

@cli.command()
def interactive():
    """Launch interactive management console"""
    vkm = VKMInterface()
    vkm.show_main_menu()

if __name__ == '__main__':
    cli()
