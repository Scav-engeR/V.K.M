#!/usr/bin/env python3
"""
VPS Kernel Manager - Advanced Linux Kernel Management Tool
For Debian 10 (Buster) and compatible systems

Features:
- Interactive CLI with rich interface
- Kernel switching and management
- Automated compilation with optimizations
- Patch management and application
- VPS-specific optimizations
- Performance benchmarking
- Security hardening
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
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import shutil
import re

try:
    import click
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.columns import Columns
    from rich.layout import Layout
    from rich.live import Live
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    print("Warning: 'rich' and 'click' not installed. Run: pip3 install rich click")

class VKMConfig:
    """Configuration manager for VPS Kernel Manager"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or os.path.expanduser("~/.vkm/config.ini")
        self.config_dir = os.path.dirname(self.config_path)
        self.config = configparser.ConfigParser()
        self.ensure_config_dir()
        self.load_config()
    
    def ensure_config_dir(self):
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(os.path.join(self.config_dir, "patches"), exist_ok=True)
        os.makedirs(os.path.join(self.config_dir, "kernels"), exist_ok=True)
        os.makedirs(os.path.join(self.config_dir, "logs"), exist_ok=True)
    
    def load_config(self):
        if os.path.exists(self.config_path):
            self.config.read(self.config_path)
        else:
            self.create_default_config()
    
    def create_default_config(self):
        self.config['general'] = {
            'build_dir': '/tmp/vkm-build',
            'kernel_source_dir': '/usr/src',
            'default_optimization': 'O2',
            'parallel_jobs': str(os.cpu_count()),
            'auto_backup': 'true',
            'max_kernels': '5'
        }
        
        self.config['compilation'] = {
            'compiler': 'gcc',
            'enable_lto': 'false',
            'enable_pgo': 'false',
            'custom_cflags': '-march=native',
            'debug_info': 'false'
        }
        
        self.config['vps'] = {
            'tcp_congestion': 'bbr',
            'io_scheduler': 'mq-deadline',
            'transparent_hugepages': 'madvise',
            'vm_swappiness': '1',
            'enable_thp': 'true'
        }
        
        self.config['security'] = {
            'enable_hardening': 'true',
            'secure_boot': 'false',
            'sign_modules': 'false',
            'audit_logging': 'true'
        }
        
        self.config['patches'] = {
            'auto_download': 'true',
            'patch_sources': 'https://github.com/xanmod/linux-patches',
            'security_patches': 'true',
            'performance_patches': 'true'
        }
        
        self.save_config()
    
    def save_config(self):
        with open(self.config_path, 'w') as f:
            self.config.write(f)
    
    def get(self, section: str, key: str, fallback=None):
        return self.config.get(section, key, fallback=fallback)
    
    def set(self, section: str, key: str, value: str):
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value
        self.save_config()

class VKMLogger:
    """Logging system for VKM operations"""
    
    def __init__(self, config: VKMConfig):
        self.config = config
        self.log_dir = os.path.join(config.config_dir, "logs")
        self.log_file = os.path.join(self.log_dir, f"vkm_{datetime.now().strftime('%Y%m%d')}.log")
        
        if HAS_RICH:
            self.console = Console()
    
    def log(self, level: str, message: str, show_console: bool = True):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        
        with open(self.log_file, 'a') as f:
            f.write(log_entry)
        
        if show_console and HAS_RICH:
            color_map = {
                'INFO': 'blue',
                'WARNING': 'yellow', 
                'ERROR': 'red',
                'SUCCESS': 'green',
                'DEBUG': 'dim'
            }
            self.console.print(f"[{color_map.get(level, 'white')}][{level}][/] {message}")
        elif show_console:
            print(f"[{level}] {message}")
    
    def info(self, message: str): self.log('INFO', message)
    def warning(self, message: str): self.log('WARNING', message)
    def error(self, message: str): self.log('ERROR', message)
    def success(self, message: str): self.log('SUCCESS', message)
    def debug(self, message: str): self.log('DEBUG', message)

class SystemInfo:
    """System information gathering"""
    
    @staticmethod
    def get_current_kernel() -> str:
        return subprocess.check_output(['uname', '-r']).decode().strip()
    
    @staticmethod
    def get_available_kernels() -> List[str]:
        try:
            result = subprocess.run(['dpkg', '--get-selections'], 
                                  capture_output=True, text=True, check=True)
            kernels = []
            for line in result.stdout.split('\n'):
                if 'linux-image-' in line and 'install' in line:
                    kernel = line.split()[0].replace('linux-image-', '')
                    if kernel != 'amd64':  # Skip meta-packages
                        kernels.append(kernel)
            return sorted(kernels, reverse=True)
        except subprocess.CalledProcessError:
            return []
    
    @staticmethod
    def get_system_info() -> Dict:
        info = {}
        try:
            # CPU info
            with open('/proc/cpuinfo', 'r') as f:
                cpu_info = f.read()
                info['cpu_cores'] = cpu_info.count('processor')
                info['cpu_model'] = re.search(r'model name\s*:\s*(.+)', cpu_info)
                info['cpu_model'] = info['cpu_model'].group(1) if info['cpu_model'] else 'Unknown'
            
            # Memory info
            with open('/proc/meminfo', 'r') as f:
                mem_info = f.read()
                mem_total = re.search(r'MemTotal:\s*(\d+)', mem_info)
                info['memory_gb'] = int(mem_total.group(1)) // 1024 // 1024 if mem_total else 0
            
            # Distribution info
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    os_info = f.read()
                    name_match = re.search(r'PRETTY_NAME="([^"]+)"', os_info)
                    info['distribution'] = name_match.group(1) if name_match else 'Unknown'
            
            # Virtualization check
            try:
                virt_result = subprocess.run(['systemd-detect-virt'], 
                                           capture_output=True, text=True)
                info['virtualization'] = virt_result.stdout.strip() if virt_result.returncode == 0 else 'none'
            except FileNotFoundError:
                info['virtualization'] = 'unknown'
                
        except Exception as e:
            info['error'] = str(e)
        
        return info

class KernelManager:
    """Core kernel management functionality"""
    
    def __init__(self, config: VKMConfig, logger: VKMLogger):
        self.config = config
        self.logger = logger
    
    def list_kernels(self) -> List[Dict]:
        """List all available kernels with metadata"""
        kernels = []
        current = SystemInfo.get_current_kernel()
        available = SystemInfo.get_available_kernels()
        
        for kernel in available:
            kernel_info = {
                'version': kernel,
                'current': kernel == current,
                'installed': True,
                'source': 'package'
            }
            kernels.append(kernel_info)
        
        return kernels
    
    def switch_kernel(self, target_kernel: str) -> bool:
        """Switch to specified kernel version"""
        try:
            self.logger.info(f"Switching to kernel {target_kernel}")
            
            # Find GRUB entry for target kernel
            grub_entries = self._get_grub_entries()
            target_entry = None
            
            for entry in grub_entries:
                if target_kernel in entry['title']:
                    target_entry = entry
                    break
            
            if not target_entry:
                self.logger.error(f"GRUB entry not found for kernel {target_kernel}")
                return False
            
            # Set default GRUB entry
            subprocess.run(['grub-set-default', target_entry['id']], check=True)
            subprocess.run(['update-grub'], check=True)
            
            self.logger.success(f"Kernel switched to {target_kernel}. Reboot required.")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to switch kernel: {e}")
            return False
    
    def _get_grub_entries(self) -> List[Dict]:
        """Parse GRUB entries"""
        entries = []
        try:
            result = subprocess.run(['grep', '-E', '^menuentry|^submenu', '/boot/grub/grub.cfg'],
                                  capture_output=True, text=True, check=True)
            
            entry_id = 0
            for line in result.stdout.split('\n'):
                if 'menuentry' in line:
                    title_match = re.search(r"'([^']+)'", line)
                    if title_match:
                        entries.append({
                            'id': str(entry_id),
                            'title': title_match.group(1)
                        })
                        entry_id += 1
        except subprocess.CalledProcessError:
            pass
        
        return entries
    
    def backup_current_kernel(self) -> bool:
        """Create backup of current kernel configuration"""
        try:
            current_kernel = SystemInfo.get_current_kernel()
            backup_dir = os.path.join(self.config.config_dir, "kernels", current_kernel)
            os.makedirs(backup_dir, exist_ok=True)
            
            # Backup kernel files
            kernel_files = [
                f'/boot/vmlinuz-{current_kernel}',
                f'/boot/initrd.img-{current_kernel}',
                f'/boot/System.map-{current_kernel}',
                f'/boot/config-{current_kernel}'
            ]
            
            for file_path in kernel_files:
                if os.path.exists(file_path):
                    shutil.copy2(file_path, backup_dir)
            
            # Save module list
            modules_result = subprocess.run(['lsmod'], capture_output=True, text=True)
            with open(os.path.join(backup_dir, 'modules.txt'), 'w') as f:
                f.write(modules_result.stdout)
            
            self.logger.success(f"Kernel {current_kernel} backed up to {backup_dir}")
            return True
            
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            return False

class KernelCompiler:
    """Automated kernel compilation with optimizations"""
    
    def __init__(self, config: VKMConfig, logger: VKMLogger):
        self.config = config
        self.logger = logger
        self.build_dir = config.get('general', 'build_dir')
    
    def download_kernel_source(self, version: str = "latest") -> bool:
        """Download kernel source code"""
        try:
            self.logger.info(f"Downloading kernel source {version}")
            
            if version == "latest":
                # Get latest stable version from kernel.org
                response = requests.get("https://www.kernel.org/releases.json")
                data = response.json()
                version = data['latest_stable']['version']
            
            kernel_url = f"https://cdn.kernel.org/pub/linux/kernel/v{version[0]}.x/linux-{version}.tar.xz"
            
            os.makedirs(self.build_dir, exist_ok=True)
            os.chdir(self.build_dir)
            
            # Download with progress
            self.logger.info(f"Downloading from {kernel_url}")
            subprocess.run(['wget', '-c', kernel_url], check=True)
            
            # Extract
            self.logger.info("Extracting kernel source")
            subprocess.run(['tar', '-xf', f'linux-{version}.tar.xz'], check=True)
            
            self.logger.success(f"Kernel source {version} downloaded and extracted")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to download kernel source: {e}")
            return False
    
    def configure_kernel(self, source_dir: str, optimization_level: str = "vps") -> bool:
        """Configure kernel with VPS optimizations"""
        try:
            os.chdir(source_dir)
            
            # Start with current config if available
            current_config = f"/boot/config-{SystemInfo.get_current_kernel()}"
            if os.path.exists(current_config):
                shutil.copy2(current_config, ".config")
                subprocess.run(['make', 'olddefconfig'], check=True)
            else:
                subprocess.run(['make', 'defconfig'], check=True)
            
            # Apply VPS-specific optimizations
            optimizations = self._get_vps_optimizations(optimization_level)
            self._apply_kernel_config(optimizations)
            
            self.logger.success("Kernel configured with VPS optimizations")
            return True
            
        except Exception as e:
            self.logger.error(f"Kernel configuration failed: {e}")
            return False
    
    def _get_vps_optimizations(self, level: str) -> Dict[str, str]:
        """Get VPS-specific kernel optimizations"""
        base_config = {
            # Virtualization support
            'CONFIG_VIRTUALIZATION': 'y',
            'CONFIG_KVM_GUEST': 'y',
            'CONFIG_PARAVIRT': 'y',
            'CONFIG_PARAVIRT_SPINLOCKS': 'y',
            
            # Network optimizations
            'CONFIG_TCP_CONG_BBR': 'y',
            'CONFIG_DEFAULT_TCP_CONG': '"bbr"',
            'CONFIG_NET_SCH_FQ': 'y',
            
            # I/O optimizations  
            'CONFIG_MQ_IOSCHED_DEADLINE': 'y',
            'CONFIG_IOSCHED_BFQ': 'y',
            
            # Memory management
            'CONFIG_TRANSPARENT_HUGEPAGE': 'y',
            'CONFIG_TRANSPARENT_HUGEPAGE_ALWAYS': 'n',
            'CONFIG_TRANSPARENT_HUGEPAGE_MADVISE': 'y',
            
            # Security hardening
            'CONFIG_SECURITY': 'y',
            'CONFIG_SECURITY_DMESG_RESTRICT': 'y',
            'CONFIG_SECURITY_SELINUX': 'n',  # Disable SELinux for performance
            'CONFIG_HARDENED_USERCOPY': 'y',
            
            # Performance
            'CONFIG_PREEMPT_VOLUNTARY': 'y',
            'CONFIG_HZ_1000': 'y',
            'CONFIG_NO_HZ_FULL': 'y',
        }
        
        if level == "performance":
            base_config.update({
                'CONFIG_PREEMPT': 'y',
                'CONFIG_HZ_1000': 'y',
                'CONFIG_FAIR_GROUP_SCHED': 'n',
            })
        elif level == "minimal":
            base_config.update({
                'CONFIG_MODULES': 'n',  # Monolithic kernel
                'CONFIG_DEBUG_KERNEL': 'n',
                'CONFIG_DEBUG_INFO': 'n',
            })
        
        return base_config
    
    def _apply_kernel_config(self, config_options: Dict[str, str]):
        """Apply configuration options to kernel"""
        for option, value in config_options.items():
            if value == 'y':
                subprocess.run(['scripts/config', '--enable', option.replace('CONFIG_', '')], 
                             check=False)
            elif value == 'n':
                subprocess.run(['scripts/config', '--disable', option.replace('CONFIG_', '')], 
                             check=False)
            else:
                subprocess.run(['scripts/config', '--set-str', option.replace('CONFIG_', ''), value], 
                             check=False)
    
    def compile_kernel(self, source_dir: str) -> bool:
        """Compile kernel with optimizations"""
        try:
            os.chdir(source_dir)
            
            # Get compilation settings
            jobs = self.config.get('general', 'parallel_jobs', str(os.cpu_count()))
            compiler = self.config.get('compilation', 'compiler', 'gcc')
            optimization = self.config.get('general', 'default_optimization', 'O2')
            
            # Build environment
            env = os.environ.copy()
            
            # Compiler optimizations
            cflags = [f'-{optimization}']
            if self.config.get('compilation', 'custom_cflags'):
                cflags.append(self.config.get('compilation', 'custom_cflags'))
            
            env['KCFLAGS'] = ' '.join(cflags)
            
            if compiler == 'clang':
                env['CC'] = 'clang'
                env['HOSTCC'] = 'clang'
                if self.config.get('compilation', 'enable_lto') == 'true':
                    env['KCFLAGS'] += ' -flto=thin'
            
            # Disable debug info for smaller size
            if self.config.get('compilation', 'debug_info') == 'false':
                subprocess.run(['scripts/config', '--disable', 'DEBUG_INFO'], check=False)
            
            self.logger.info(f"Starting kernel compilation with {jobs} jobs")
            
            # Compile kernel
            subprocess.run(['make', f'-j{jobs}', 'bindeb-pkg'], 
                         env=env, check=True)
            
            self.logger.success("Kernel compilation completed")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Kernel compilation failed: {e}")
            return False
    
    def install_compiled_kernel(self, source_dir: str) -> bool:
        """Install compiled kernel packages"""
        try:
            parent_dir = os.path.dirname(source_dir)
            
            # Find generated .deb packages
            deb_files = []
            for file in os.listdir(parent_dir):
                if file.endswith('.deb') and 'linux-image' in file:
                    deb_files.append(os.path.join(parent_dir, file))
            
            if not deb_files:
                self.logger.error("No kernel .deb packages found")
                return False
            
            # Install packages
            for deb_file in deb_files:
                self.logger.info(f"Installing {deb_file}")
                subprocess.run(['dpkg', '-i', deb_file], check=True)
            
            # Update GRUB
            subprocess.run(['update-grub'], check=True)
            
            self.logger.success("Compiled kernel installed successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Kernel installation failed: {e}")
            return False

class PatchManager:
    """Kernel patch management and application"""
    
    def __init__(self, config: VKMConfig, logger: VKMLogger):
        self.config = config
        self.logger = logger
        self.patch_dir = os.path.join(config.config_dir, "patches")
    
    def download_patch(self, url: str, patch_name: str = None) -> str:
        """Download patch from URL"""
        try:
            if not patch_name:
                patch_name = os.path.basename(url)
            
            patch_path = os.path.join(self.patch_dir, patch_name)
            
            self.logger.info(f"Downloading patch from {url}")
            response = requests.get(url)
            response.raise_for_status()
            
            with open(patch_path, 'wb') as f:
                f.write(response.content)
            
            self.logger.success(f"Patch downloaded: {patch_path}")
            return patch_path
            
        except Exception as e:
            self.logger.error(f"Failed to download patch: {e}")
            return None
    
    def apply_patch(self, patch_path: str, source_dir: str, reverse: bool = False) -> bool:
        """Apply patch to kernel source"""
        try:
            os.chdir(source_dir)
            
            cmd = ['patch', '-p1']
            if reverse:
                cmd.append('-R')
            
            with open(patch_path, 'r') as f:
                result = subprocess.run(cmd, stdin=f, capture_output=True, text=True)
            
            if result.returncode == 0:
                action = "reversed" if reverse else "applied"
                self.logger.success(f"Patch {action}: {patch_path}")
                return True
            else:
                self.logger.error(f"Patch failed: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Patch application failed: {e}")
            return False
    
    def get_xanmod_patches(self) -> List[str]:
        """Get available XanMod performance patches"""
        patches = []
        try:
            # Common XanMod patches for VPS optimization
            xanmod_patches = [
                "bbr2.patch",
                "cacule-scheduler.patch", 
                "le9-patches.patch",
                "multigenerational-lru.patch",
                "tcp-optimizations.patch"
            ]
            
            for patch in xanmod_patches:
                patch_url = f"https://raw.githubusercontent.com/xanmod/linux-patches/master/{patch}"
                downloaded = self.download_patch(patch_url, f"xanmod-{patch}")
                if downloaded:
                    patches.append(downloaded)
                    
        except Exception as e:
            self.logger.warning(f"Could not download XanMod patches: {e}")
        
        return patches
    
    def get_security_patches(self, kernel_version: str) -> List[str]:
        """Get security patches for kernel version"""
        patches = []
        # Implementation would fetch from security advisories
        # This is a placeholder for the actual implementation
        self.logger.info(f"Checking security patches for {kernel_version}")
        return patches

class VPSOptimizer:
    """VPS-specific system optimizations"""
    
    def __init__(self, config: VKMConfig, logger: VKMLogger):
        self.config = config
        self.logger = logger
    
    def apply_network_optimizations(self) -> bool:
        """Apply network optimizations for VPS"""
        try:
            optimizations = {
                'net.core.rmem_default': '262144',
                'net.core.rmem_max': '268435456',
                'net.core.wmem_default': '262144', 
                'net.core.wmem_max': '268435456',
                'net.core.netdev_max_backlog': '5000',
                'net.core.default_qdisc': 'fq',
                'net.ipv4.tcp_congestion_control': self.config.get('vps', 'tcp_congestion', 'bbr'),
                'net.ipv4.tcp_rmem': '4096 16384 268435456',
                'net.ipv4.tcp_wmem': '4096 65536 268435456',
                'net.ipv4.tcp_fastopen': '3',
                'net.ipv4.tcp_window_scaling': '1',
                'net.ipv4.tcp_timestamps': '1',
                'net.ipv4.tcp_sack': '1',
                'net.ipv4.tcp_no_metrics_save': '1',
            }
            
            sysctl_conf = "/etc/sysctl.d/99-vkm-network.conf"
            with open(sysctl_conf, 'w') as f:
                f.write("# VKM Network Optimizations\n")
                for param, value in optimizations.items():
                    f.write(f"{param} = {value}\n")
            
            subprocess.run(['sysctl', '-p', sysctl_conf], check=True)
            self.logger.success("Network optimizations applied")
            return True
            
        except Exception as e:
            self.logger.error(f"Network optimization failed: {e}")
            return False
    
    def apply_memory_optimizations(self) -> bool:
        """Apply memory optimizations for VPS"""
        try:
            optimizations = {
                'vm.swappiness': self.config.get('vps', 'vm_swappiness', '1'),
                'vm.vfs_cache_pressure': '10',
                'vm.dirty_background_ratio': '5',
                'vm.dirty_ratio': '10',
                'vm.dirty_expire_centisecs': '1500',
                'vm.dirty_writeback_centisecs': '500',
                'vm.overcommit_memory': '1',
                'vm.overcommit_ratio': '50',
            }
            
            sysctl_conf = "/etc/sysctl.d/99-vkm-memory.conf"
            with open(sysctl_conf, 'w') as f:
                f.write("# VKM Memory Optimizations\n")
                for param, value in optimizations.items():
                    f.write(f"{param} = {value}\n")
            
            subprocess.run(['sysctl', '-p', sysctl_conf], check=True)
            
            # Configure transparent huge pages
            thp_setting = self.config.get('vps', 'transparent_hugepages', 'madvise')
            with open('/sys/kernel/mm/transparent_hugepage/enabled', 'w') as f:
                f.write(thp_setting)
            
            self.logger.success("Memory optimizations applied")
            return True
            
        except Exception as e:
            self.logger.error(f"Memory optimization failed: {e}")
            return False
    
    def apply_io_optimizations(self) -> bool:
        """Apply I/O optimizations for VPS"""
        try:
            scheduler = self.config.get('vps', 'io_scheduler', 'mq-deadline')
            
            # Set I/O scheduler for all block devices
            for device in os.listdir('/sys/block'):
                if not device.startswith('loop') and not device.startswith('ram'):
                    scheduler_path = f'/sys/block/{device}/queue/scheduler'
                    if os.path.exists(scheduler_path):
                        try:
                            with open(scheduler_path, 'w') as f:
                                f.write(scheduler)
                        except:
                            pass  # Some devices may not support scheduler changes
            
            self.logger.success(f"I/O scheduler set to {scheduler}")
            return True
            
        except Exception as e:
            self.logger.error(f"I/O optimization failed: {e}")
            return False

class PerformanceBenchmark:
    """Performance benchmarking and validation"""
    
    def __init__(self, logger: VKMLogger):
        self.logger = logger
    
    def run_network_benchmark(self) -> Dict:
        """Run network performance benchmark"""
        results = {}
        try:
            # Test TCP BBR if available
            if os.path.exists('/proc/sys/net/ipv4/tcp_congestion_control'):
                with open('/proc/sys/net/ipv4/tcp_congestion_control', 'r') as f:
                    results['tcp_congestion'] = f.read().strip()
            
            # Test network throughput using iperf3 if available
            try:
                iperf_result = subprocess.run(['iperf3', '--version'], 
                                            capture_output=True, text=True)
                if iperf_result.returncode == 0:
                    results['iperf3_available'] = True
                    # Could run actual iperf3 test here
                else:
                    results['iperf3_available'] = False
            except FileNotFoundError:
                results['iperf3_available'] = False
            
        except Exception as e:
            self.logger.error(f"Network benchmark failed: {e}")
        
        return results
    
    def run_disk_benchmark(self) -> Dict:
        """Run disk I/O benchmark"""
                    results = {}
        try:
            # Check current I/O scheduler
            schedulers = {}
            for device in os.listdir('/sys/block'):
                if not device.startswith('loop') and not device.startswith('ram'):
                    scheduler_path = f'/sys/block/{device}/queue/scheduler'
                    if os.path.exists(scheduler_path):
                        with open(scheduler_path, 'r') as f:
                            current = re.search(r'\[([^\]]+)\]', f.read())
                            if current:
                                schedulers[device] = current.group(1)
            
            results['io_schedulers'] = schedulers
            
            # Simple disk speed test using dd
            self.logger.info("Running disk benchmark...")
            dd_result = subprocess.run([
                'dd', 'if=/dev/zero', 'of=/tmp/vkm_test', 'bs=1M', 'count=100', 'oflag=direct'
            ], capture_output=True, text=True, timeout=30)
            
            if dd_result.returncode == 0:
                # Parse dd output for speed
                speed_match = re.search(r'(\d+\.?\d*)\s*[MGK]?B/s', dd_result.stderr)
                if speed_match:
                    results['disk_write_speed'] = speed_match.group(0)
            
            # Cleanup test file
            if os.path.exists('/tmp/vkm_test'):
                os.remove('/tmp/vkm_test')
                
        except Exception as e:
            self.logger.error(f"Disk benchmark failed: {e}")
        
        return results
    
    def run_memory_benchmark(self) -> Dict:
        """Run memory performance benchmark"""
        results = {}
        try:
            # Get memory info
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
            
            # Parse memory information
            mem_total = re.search(r'MemTotal:\s*(\d+)', meminfo)
            mem_available = re.search(r'MemAvailable:\s*(\d+)', meminfo)
            
            if mem_total:
                results['total_memory_kb'] = int(mem_total.group(1))
            if mem_available:
                results['available_memory_kb'] = int(mem_available.group(1))
            
            # Check transparent huge pages
            if os.path.exists('/sys/kernel/mm/transparent_hugepage/enabled'):
                with open('/sys/kernel/mm/transparent_hugepage/enabled', 'r') as f:
                    thp_status = f.read().strip()
                    thp_match = re.search(r'\[([^\]]+)\]', thp_status)
                    if thp_match:
                        results['transparent_hugepages'] = thp_match.group(1)
            
            # Check vm settings
            vm_settings = ['swappiness', 'vfs_cache_pressure', 'dirty_ratio']
            for setting in vm_settings:
                setting_path = f'/proc/sys/vm/{setting}'
                if os.path.exists(setting_path):
                    with open(setting_path, 'r') as f:
                        results[f'vm_{setting}'] = f.read().strip()
                        
        except Exception as e:
            self.logger.error(f"Memory benchmark failed: {e}")
        
        return results

class SecurityManager:
    """Security hardening and management"""
    
    def __init__(self, config: VKMConfig, logger: VKMLogger):
        self.config = config
        self.logger = logger
    
    def apply_security_hardening(self) -> bool:
        """Apply kernel security hardening"""
        try:
            hardening_options = {
                'kernel.dmesg_restrict': '1',
                'kernel.kptr_restrict': '2',
                'kernel.yama.ptrace_scope': '1',
                'kernel.unprivileged_userns_clone': '0',
                'net.ipv4.conf.all.send_redirects': '0',
                'net.ipv4.conf.default.send_redirects': '0',
                'net.ipv4.conf.all.accept_redirects': '0',
                'net.ipv4.conf.default.accept_redirects': '0',
                'net.ipv4.conf.all.secure_redirects': '0',
                'net.ipv4.conf.default.secure_redirects': '0',
                'net.ipv4.ip_forward': '0',
                'net.ipv6.conf.all.accept_redirects': '0',
                'net.ipv6.conf.default.accept_redirects': '0',
            }
            
            sysctl_conf = "/etc/sysctl.d/99-vkm-security.conf"
            with open(sysctl_conf, 'w') as f:
                f.write("# VKM Security Hardening\n")
                for param, value in hardening_options.items():
                    f.write(f"{param} = {value}\n")
            
            subprocess.run(['sysctl', '-p', sysctl_conf], check=True)
            self.logger.success("Security hardening applied")
            return True
            
        except Exception as e:
            self.logger.error(f"Security hardening failed: {e}")
            return False
    
    def setup_audit_logging(self) -> bool:
        """Setup kernel audit logging"""
        try:
            # Install auditd if not present
            if not shutil.which('auditctl'):
                subprocess.run(['apt', 'update'], check=True)
                subprocess.run(['apt', 'install', '-y', 'auditd'], check=True)
            
            # Basic audit rules
            audit_rules = [
                "# VKM Audit Rules",
                "-D",
                "-b 8192",
                "-f 1",
                "",
                "# Monitor kernel module loading",
                "-w /sbin/insmod -p x -k modules",
                "-w /sbin/rmmod -p x -k modules",
                "-w /sbin/modprobe -p x -k modules",
                "",
                "# Monitor important files",
                "-w /etc/passwd -p wa -k passwd_changes",
                "-w /etc/group -p wa -k group_changes",
                "-w /etc/shadow -p wa -k shadow_changes",
                "",
                "# Monitor syscalls",
                "-a always,exit -F arch=b64 -S adjtimex -S settimeofday -k time-change",
                "-a always,exit -F arch=b32 -S adjtimex -S settimeofday -S stime -k time-change",
            ]
            
            with open('/etc/audit/rules.d/vkm.rules', 'w') as f:
                f.write('\n'.join(audit_rules))
            
            # Restart auditd
            subprocess.run(['systemctl', 'restart', 'auditd'], check=True)
            subprocess.run(['systemctl', 'enable', 'auditd'], check=True)
            
            self.logger.success("Audit logging configured")
            return True
            
        except Exception as e:
            self.logger.error(f"Audit logging setup failed: {e}")
            return False

class VKMInterface:
    """Rich CLI interface for VKM"""
    
    def __init__(self):
        self.config = VKMConfig()
        self.logger = VKMLogger(self.config)
        self.kernel_manager = KernelManager(self.config, self.logger)
        self.compiler = KernelCompiler(self.config, self.logger)
        self.patch_manager = PatchManager(self.config, self.logger)
        self.optimizer = VPSOptimizer(self.config, self.logger)
        self.benchmark = PerformanceBenchmark(self.logger)
        self.security = SecurityManager(self.config, self.logger)
        
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

VPS Kernel Manager v1.0
Advanced Linux Kernel Management
Debian 10 (Buster) Compatible
        """
        
        if HAS_RICH:
            self.console.print(Panel(banner, style="bold blue", title="Welcome"))
        else:
            print(banner)
    
    def show_system_info(self):
        """Display system information"""
        info = SystemInfo.get_system_info()
        current_kernel = SystemInfo.get_current_kernel()
        
        if HAS_RICH:
            table = Table(title="System Information")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="magenta")
            
            table.add_row("Current Kernel", current_kernel)
            table.add_row("Distribution", info.get('distribution', 'Unknown'))
            table.add_row("CPU Model", info.get('cpu_model', 'Unknown'))
            table.add_row("CPU Cores", str(info.get('cpu_cores', 'Unknown')))
            table.add_row("Memory", f"{info.get('memory_gb', 'Unknown')} GB")
            table.add_row("Virtualization", info.get('virtualization', 'Unknown'))
            
            self.console.print(table)
        else:
            print(f"\nSystem Information:")
            print(f"Current Kernel: {current_kernel}")
            print(f"Distribution: {info.get('distribution', 'Unknown')}")
            print(f"CPU: {info.get('cpu_model', 'Unknown')} ({info.get('cpu_cores', 'Unknown')} cores)")
            print(f"Memory: {info.get('memory_gb', 'Unknown')} GB")
            print(f"Virtualization: {info.get('virtualization', 'Unknown')}")
    
    def show_kernel_list(self):
        """Display available kernels"""
        kernels = self.kernel_manager.list_kernels()
        
        if HAS_RICH:
            table = Table(title="Available Kernels")
            table.add_column("Version", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Source", style="yellow")
            
            for kernel in kernels:
                status = "Current" if kernel['current'] else "Available"
                table.add_row(kernel['version'], status, kernel['source'])
            
            self.console.print(table)
        else:
            print("\nAvailable Kernels:")
            for kernel in kernels:
                status = " (current)" if kernel['current'] else ""
                print(f"  {kernel['version']}{status}")
    
    def interactive_menu(self):
        """Main interactive menu"""
        while True:
            if HAS_RICH:
                self.console.print("\n[bold cyan]VKM Main Menu[/bold cyan]")
                choices = [
                    "1. System Information",
                    "2. List Kernels", 
                    "3. Switch Kernel",
                    "4. Compile Custom Kernel",
                    "5. Apply Patches", 
                    "6. VPS Optimizations",
                    "7. Security Hardening",
                    "8. Performance Benchmark",
                    "9. Configuration",
                    "0. Exit"
                ]
                
                for choice in choices:
                    self.console.print(f"  {choice}")
                
                selection = Prompt.ask("\nSelect option", choices=[str(i) for i in range(10)])
            else:
                print("\nVKM Main Menu:")
                print("1. System Information")
                print("2. List Kernels")
                print("3. Switch Kernel") 
                print("4. Compile Custom Kernel")
                print("5. Apply Patches")
                print("6. VPS Optimizations")
                print("7. Security Hardening")
                print("8. Performance Benchmark")
                print("9. Configuration")
                print("0. Exit")
                selection = input("\nSelect option: ")
            
            if selection == "1":
                self.show_system_info()
            elif selection == "2":
                self.show_kernel_list()
            elif selection == "3":
                self.handle_kernel_switch()
            elif selection == "4":
                self.handle_kernel_compilation()
            elif selection == "5":
                self.handle_patch_management()
            elif selection == "6":
                self.handle_vps_optimization()
            elif selection == "7":
                self.handle_security_hardening()
            elif selection == "8":
                self.handle_performance_benchmark()
            elif selection == "9":
                self.handle_configuration()
            elif selection == "0":
                if HAS_RICH:
                    self.console.print("[bold green]Goodbye![/bold green]")
                else:
                    print("Goodbye!")
                break
            else:
                if HAS_RICH:
                    self.console.print("[bold red]Invalid selection[/bold red]")
                else:
                    print("Invalid selection")
    
    def handle_kernel_switch(self):
        """Handle kernel switching"""
        kernels = self.kernel_manager.list_kernels()
        available_kernels = [k['version'] for k in kernels if not k['current']]
        
        if not available_kernels:
            self.logger.warning("No other kernels available")
            return
        
        if HAS_RICH:
            target = Prompt.ask("Select kernel to switch to", choices=available_kernels)
            if Confirm.ask(f"Switch to kernel {target}?"):
                self.kernel_manager.switch_kernel(target)
        else:
            print("\nAvailable kernels:")
            for i, kernel in enumerate(available_kernels):
                print(f"{i+1}. {kernel}")
            
            try:
                choice = int(input("Select kernel number: ")) - 1
                target = available_kernels[choice]
                confirm = input(f"Switch to kernel {target}? (y/N): ")
                if confirm.lower() == 'y':
                    self.kernel_manager.switch_kernel(target)
            except (ValueError, IndexError):
                print("Invalid selection")
    
    def handle_kernel_compilation(self):
        """Handle custom kernel compilation"""
        if HAS_RICH:
            self.console.print("[bold yellow]Custom Kernel Compilation[/bold yellow]")
            
            version = Prompt.ask("Kernel version", default="latest")
            optimization = Prompt.ask("Optimization level", 
                                    choices=["vps", "performance", "minimal"], 
                                    default="vps")
            
            if Confirm.ask("Download and compile kernel?"):
                with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
                    task = progress.add_task("Downloading kernel source...", total=None)
                    
                    if self.compiler.download_kernel_source(version):
                        progress.update(task, description="Configuring kernel...")
                        source_dir = os.path.join(self.compiler.build_dir, f"linux-{version}")
                        
                        if self.compiler.configure_kernel(source_dir, optimization):
                            progress.update(task, description="Compiling kernel...")
                            
                            if self.compiler.compile_kernel(source_dir):
                                progress.update(task, description="Installing kernel...")
                                self.compiler.install_compiled_kernel(source_dir)
        else:
            print("\nCustom Kernel Compilation")
            version = input("Kernel version (latest): ") or "latest"
            print("Optimization levels: vps, performance, minimal")
            optimization = input("Optimization level (vps): ") or "vps"
            
            confirm = input("Download and compile kernel? (y/N): ")
            if confirm.lower() == 'y':
                print("Downloading kernel source...")
                if self.compiler.download_kernel_source(version):
                    print("Configuring kernel...")
                    source_dir = os.path.join(self.compiler.build_dir, f"linux-{version}")
                    
                    if self.compiler.configure_kernel(source_dir, optimization):
                        print("Compiling kernel...")
                        if self.compiler.compile_kernel(source_dir):
                            print("Installing kernel...")
                            self.compiler.install_compiled_kernel(source_dir)
    
    def handle_patch_management(self):
        """Handle patch management"""
        if HAS_RICH:
            self.console.print("[bold yellow]Patch Management[/bold yellow]")
            
            patch_type = Prompt.ask("Patch type", 
                                  choices=["xanmod", "security", "custom"], 
                                  default="xanmod")
            
            if patch_type == "xanmod":
                if Confirm.ask("Download XanMod performance patches?"):
                    patches = self.patch_manager.get_xanmod_patches()
                    self.logger.info(f"Downloaded {len(patches)} XanMod patches")
            
            elif patch_type == "custom":
                url = Prompt.ask("Patch URL")
                name = Prompt.ask("Patch name (optional)", default="")
                self.patch_manager.download_patch(url, name or None)
        else:
            print("\nPatch Management")
            print("1. XanMod performance patches")
            print("2. Security patches") 
            print("3. Custom patch URL")
            
            choice = input("Select option: ")
            if choice == "1":
                patches = self.patch_manager.get_xanmod_patches()
                print(f"Downloaded {len(patches)} XanMod patches")
            elif choice == "3":
                url = input("Patch URL: ")
                name = input("Patch name (optional): ")
                self.patch_manager.download_patch(url, name or None)
    
    def handle_vps_optimization(self):
        """Handle VPS optimizations"""
        if HAS_RICH:
            self.console.print("[bold yellow]VPS Optimizations[/bold yellow]")
            
            optimizations = [
                ("Network", "network"),
                ("Memory", "memory"), 
                ("I/O", "io"),
                ("All", "all")
            ]
            
            choices = [opt[1] for opt in optimizations]
            selection = Prompt.ask("Select optimization", choices=choices, default="all")
        else:
            print("\nVPS Optimizations:")
            print("1. Network optimizations")
            print("2. Memory optimizations")
            print("3. I/O optimizations") 
            print("4. All optimizations")
            
            choice = input("Select option: ")
            selection_map = {"1": "network", "2": "memory", "3": "io", "4": "all"}
            selection = selection_map.get(choice, "all")
        
        if selection in ["network", "all"]:
            self.optimizer.apply_network_optimizations()
        if selection in ["memory", "all"]:
            self.optimizer.apply_memory_optimizations()
        if selection in ["io", "all"]:
            self.optimizer.apply_io_optimizations()
    
    def handle_security_hardening(self):
        """Handle security hardening"""
        if HAS_RICH:
            self.console.print("[bold yellow]Security Hardening[/bold yellow]")
            
            if Confirm.ask("Apply kernel security hardening?"):
                self.security.apply_security_hardening()
            
            if Confirm.ask("Setup audit logging?"):
                self.security.setup_audit_logging()
        else:
            print("\nSecurity Hardening")
            
            if input("Apply kernel security hardening? (y/N): ").lower() == 'y':
                self.security.apply_security_hardening()
            
            if input("Setup audit logging? (y/N): ").lower() == 'y':
                self.security.setup_audit_logging()
    
    def handle_performance_benchmark(self):
        """Handle performance benchmarking"""
        if HAS_RICH:
            self.console.print("[bold yellow]Performance Benchmark[/bold yellow]")
            
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
                task = progress.add_task("Running benchmarks...", total=None)
                
                progress.update(task, description="Network benchmark...")
                network_results = self.benchmark.run_network_benchmark()
                
                progress.update(task, description="Disk benchmark...")
                disk_results = self.benchmark.run_disk_benchmark()
                
                progress.update(task, description="Memory benchmark...")
                memory_results = self.benchmark.run_memory_benchmark()
            
            # Display results
            table = Table(title="Benchmark Results")
            table.add_column("Category", style="cyan")
            table.add_column("Metric", style="yellow")
            table.add_column("Value", style="green")
            
            for metric, value in network_results.items():
                table.add_row("Network", metric, str(value))
            for metric, value in disk_results.items():
                table.add_row("Disk", metric, str(value))
            for metric, value in memory_results.items():
                table.add_row("Memory", metric, str(value))
            
            self.console.print(table)
        else:
            print("\nRunning Performance Benchmark...")
            
            print("Network benchmark...")
            network_results = self.benchmark.run_network_benchmark()
            
            print("Disk benchmark...")
            disk_results = self.benchmark.run_disk_benchmark()
            
            print("Memory benchmark...")
            memory_results = self.benchmark.run_memory_benchmark()
            
            print("\nBenchmark Results:")
            print("Network:")
            for metric, value in network_results.items():
                print(f"  {metric}: {value}")
            print("Disk:")
            for metric, value in disk_results.items():
                print(f"  {metric}: {value}")
            print("Memory:")
            for metric, value in memory_results.items():
                print(f"  {metric}: {value}")
    
    def handle_configuration(self):
        """Handle configuration management"""
        if HAS_RICH:
            self.console.print("[bold yellow]Configuration[/bold yellow]")
            
            sections = list(self.config.config.sections())
            section = Prompt.ask("Select section", choices=sections)
            
            if section in self.config.config:
                for key, value in self.config.config[section].items():
                    new_value = Prompt.ask(f"{key}", default=value)
                    if new_value != value:
                        self.config.set(section, key, new_value)
        else:
            print("\nConfiguration")
            print("Available sections:")
            for section in self.config.config.sections():
                print(f"  {section}")
            
            section = input("Select section: ")
            if section in self.config.config:
                for key, value in self.config.config[section].items():
                    new_value = input(f"{key} ({value}): ") or value
                    if new_value != value:
                        self.config.set(section, key, new_value)

# CLI Commands using Click
@click.group()
@click.version_option(version="1.0.0")
def cli():
    """VPS Kernel Manager - Advanced Linux Kernel Management"""
    pass

@cli.command()
def interactive():
    """Start interactive mode"""
    vkm = VKMInterface()
    vkm.show_banner()
    vkm.interactive_menu()

@cli.command()
def info():
    """Show system information"""
    vkm = VKMInterface()
    vkm.show_system_info()

@cli.command()
def list_kernels():
    """List available kernels"""
    vkm = VKMInterface()
    vkm.show_kernel_list()

@cli.command()
@click.argument('kernel_version')
def switch(kernel_version):
    """Switch to specified kernel version"""
    vkm = VKMInterface()
    vkm.kernel_manager.switch_kernel(kernel_version)

@cli.command()
@click.option('--version', default='latest', help='Kernel version to compile')
@click.option('--optimization', default='vps', type=click.Choice(['vps', 'performance', 'minimal']))
def compile(version, optimization):
    """Compile custom kernel"""
    vkm = VKMInterface()
    
    if vkm.compiler.download_kernel_source(version):
        source_dir = os.path.join(vkm.compiler.build_dir, f"linux-{version}")
        if vkm.compiler.configure_kernel(source_dir, optimization):
            if vkm.compiler.compile_kernel(source_dir):
                vkm.compiler.install_compiled_kernel(source_dir)

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
    
    print("Running benchmarks...")
    network_results = vkm.benchmark.run_network_benchmark()
    disk_results = vkm.benchmark.run_disk_benchmark()
    memory_results = vkm.benchmark.run_memory_benchmark()
    
    print("\nResults:")
    print("Network:", network_results)
    print("Disk:", disk_results)
    print("Memory:", memory_results)

@cli.command()
@click.option('--url', help='Patch URL to download')
@click.option('--name', help='Patch name')
def patch(url, name):
    """Download and manage patches"""
    vkm = VKMInterface()
    
    if url:
        vkm.patch_manager.download_patch(url, name)
    else:
        # Download XanMod patches
        patches = vkm.patch_manager.get_xanmod_patches()
        print(f"Downloaded {len(patches)} XanMod patches")

@cli.command()
def harden():
    """Apply security hardening"""
    vkm = VKMInterface()
    vkm.security.apply_security_hardening()
    vkm.security.setup_audit_logging()

if __name__ == "__main__":
    # Check for root privileges for system operations
    if os.geteuid() != 0 and len(sys.argv) > 1 and sys.argv[1] not in ['info', 'list-kernels', '--help', '--version']:
        print("Warning: Many operations require root privileges")
        print("Run with sudo for full functionality")
    
    # Install dependencies if missing
    if not HAS_RICH:
        print("Installing required dependencies...")
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'rich', 'click', 'requests'], check=True)
            print("Dependencies installed. Please run the script again.")
            sys.exit(0)
        except subprocess.CalledProcessError:
            print("Failed to install dependencies. Please install manually:")
            print("pip3 install rich click requests")
            sys.exit(1)
    
    cli()
