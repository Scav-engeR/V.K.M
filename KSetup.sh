#!/bin/bash
# VPS Kernel Manager Installation Script
# For Debian 10 (Buster) and compatible systems

set -e

VKM_VERSION="1.0.0"
INSTALL_DIR="/opt/vkm"
BIN_DIR="/usr/local/bin"
CONFIG_DIR="/etc/vkm"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Banner
show_banner() {
    cat << 'EOF'
██╗   ██╗██╗  ██╗███╗   ███╗
██║   ██║██║ ██╔╝████╗ ████║
██║   ██║█████╔╝ ██╔████╔██║
╚██╗ ██╔╝██╔═██╗ ██║╚██╔╝██║
 ╚████╔╝ ██║  ██╗██║ ╚═╝ ██║
  ╚═══╝  ╚═╝  ╚═╝╚═╝     ╚═╝

VPS Kernel Manager Installation
Version 1.0.0

EOF
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        log_info "Please run: sudo $0"
        exit 1
    fi
}

# Detect distribution
detect_distribution() {
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        OS=$ID
        VER=$VERSION_ID
    else
        log_error "Cannot detect distribution"
        exit 1
    fi
    
    log_info "Detected: $PRETTY_NAME"
    
    if [[ "$OS" != "debian" ]] && [[ "$OS" != "ubuntu" ]]; then
        log_warning "This tool is optimized for Debian/Ubuntu systems"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Check system requirements
check_requirements() {
    log_info "Checking system requirements..."
    
    # Check available space
    AVAILABLE_SPACE=$(df /opt 2>/dev/null | tail -1 | awk '{print $4}' || echo "0")
    REQUIRED_SPACE=1048576  # 1GB in KB
    
    if [[ $AVAILABLE_SPACE -lt $REQUIRED_SPACE ]]; then
        log_error "Insufficient disk space. Required: 1GB, Available: $((AVAILABLE_SPACE/1024))MB"
        exit 1
    fi
    
    # Check memory
    TOTAL_MEM=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    MIN_MEM=524288  # 512MB in KB
    
    if [[ $TOTAL_MEM -lt $MIN_MEM ]]; then
        log_warning "Low memory detected. Kernel compilation may fail."
    fi
    
    log_success "System requirements check passed"
}

# Install dependencies
install_dependencies() {
    log_info "Installing dependencies..."
    
    # Update package list
    apt-get update -qq
    
    # Essential packages
    PACKAGES=(
        python3
        python3-pip
        wget
        curl
        build-essential
        bc
        kmod
        cpio
        flex
        libncurses5-dev
        libelf-dev
        libssl-dev
        dwarves
        bison
        git
        rsync
        grub2-common
        initramfs-tools
    )
    
    # Optional packages for enhanced functionality
    OPTIONAL_PACKAGES=(
        auditd
        iperf3
        htop
        iotop
        sysstat
        linux-source
        kernel-package
    )
    
    log_info "Installing essential packages..."
    apt-get install -y "${PACKAGES[@]}" || {
        log_error "Failed to install essential packages"
        exit 1
    }
    
    log_info "Installing optional packages..."
    for pkg in "${OPTIONAL_PACKAGES[@]}"; do
        if apt-get install -y "$pkg" 2>/dev/null; then
            log_success "Installed $pkg"
        else
            log_warning "Failed to install $pkg (optional)"
        fi
    done
    
    # Install Python dependencies
    log_info "Installing Python dependencies..."
    pip3 install --upgrade pip
    pip3 install rich click requests configparser pathlib || {
        log_error "Failed to install Python dependencies"
        exit 1
    }
    
    log_success "Dependencies installed successfully"
}

# Download and install VKM
install_vkm() {
    log_info "Installing VPS Kernel Manager..."
    
    # Create directories
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "/var/log/vkm"
    
    # Download or copy VKM script
    if [[ -f "vps_kernel_manager.py" ]]; then
        # Install from local file
        cp "vps_kernel_manager.py" "$INSTALL_DIR/vkm.py"
    else
        # Download from repository (placeholder URL)
        log_warning "Local vps_kernel_manager.py not found"
        log_info "Please ensure vps_kernel_manager.py is in the same directory"
        exit 1
    fi
    
    # Make executable
    chmod +x "$INSTALL_DIR/vkm.py"
    
    # Create symlink
    ln -sf "$INSTALL_DIR/vkm.py" "$BIN_DIR/vkm"
    
    # Create configuration file
    cat > "$CONFIG_DIR/vkm.conf" << 'EOF'
# VKM Global Configuration
[DEFAULT]
log_level = INFO
max_parallel_jobs = auto
enable_backups = true

[paths]
build_directory = /tmp/vkm-build
kernel_sources = /usr/src
patch_directory = /var/lib/vkm/patches

[security]
require_confirmation = true
audit_operations = true
EOF
    
    # Set permissions
    chown -R root:root "$INSTALL_DIR"
    chown -R root:root "$CONFIG_DIR"
    chmod 755 "$INSTALL_DIR"
    chmod 644 "$CONFIG_DIR/vkm.conf"
    
    log_success "VKM installed to $INSTALL_DIR"
}

# Create systemd service
create_service() {
    log_info "Creating systemd service..."
    
    cat > /etc/systemd/system/vkm-monitor.service << 'EOF'
[Unit]
Description=VKM Kernel Monitor
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/vkm benchmark --auto
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/vkm-monitor.timer << 'EOF'
[Unit]
Description=Run VKM Monitor Daily
Requires=vkm-monitor.service

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF

    systemctl daemon-reload
    systemctl enable vkm-monitor.timer
    
    log_success "Systemd service created"
}

# Setup bash completion
setup_completion() {
    log_info "Setting up bash completion..."
    
    cat > /etc/bash_completion.d/vkm << 'EOF'
# VKM bash completion
_vkm_completions() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    opts="interactive info list-kernels switch compile optimize benchmark patch harden --help --version"
    
    case ${prev} in
        switch)
            local kernels=$(dpkg --get-selections | grep linux-image | grep install | awk '{print $1}' | sed 's/linux-image-//')
            COMPREPLY=( $(compgen -W "${kernels}" -- ${cur}) )
            return 0
            ;;
        --optimization)
            COMPREPLY=( $(compgen -W "vps performance minimal" -- ${cur}) )
            return 0
            ;;
        --type)
            COMPREPLY=( $(compgen -W "network memory io all" -- ${cur}) )
            return 0
            ;;
    esac
    
    COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    return 0
}

complete -F _vkm_completions vkm
EOF
    
    log_success "Bash completion installed"
}

# Configure firewall if ufw is installed
configure_firewall() {
    if command -v ufw >/dev/null 2>&1; then
        log_info "Configuring UFW firewall..."
        
        # Allow SSH (important!)
        ufw allow ssh
        
        # Allow common VPS services
        ufw allow 80/tcp   # HTTP
        ufw allow 443/tcp  # HTTPS
        
        log_success "Firewall configured"
    fi
}

# Perform initial optimization
initial_optimization() {
    log_info "Applying initial VPS optimizations..."
    
    # Create basic sysctl optimizations
    cat > /etc/sysctl.d/99-vkm-initial.conf << 'EOF'
# VKM Initial Optimizations
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
vm.swappiness = 1
vm.vfs_cache_pressure = 10
EOF
    
    # Apply immediately
    sysctl -p /etc/sysctl.d/99-vkm-initial.conf >/dev/null 2>&1 || true
    
    log_success "Initial optimizations applied"
}

# Setup logging rotation
setup_logging() {
    log_info "Setting up log rotation..."
    
    cat > /etc/logrotate.d/vkm << 'EOF'
/var/log/vkm/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
    postrotate
        systemctl reload rsyslog > /dev/null 2>&1 || true
    endscript
}
EOF
    
    log_success "Log rotation configured"
}

# Create uninstall script
create_uninstaller() {
    log_info "Creating uninstaller..."
    
    cat > "$INSTALL_DIR/uninstall.sh" << 'EOF'
#!/bin/bash
# VKM Uninstaller

echo "Uninstalling VPS Kernel Manager..."

# Stop and disable services
systemctl stop vkm-monitor.timer 2>/dev/null || true
systemctl disable vkm-monitor.timer 2>/dev/null || true
rm -f /etc/systemd/system/vkm-monitor.* 2>/dev/null || true
systemctl daemon-reload

# Remove files
rm -rf /opt/vkm
rm -f /usr/local/bin/vkm
rm -f /etc/bash_completion.d/vkm
rm -f /etc/logrotate.d/vkm
rm -rf /etc/vkm

# Remove sysctl configs
rm -f /etc/sysctl.d/99-vkm-*.conf

# Remove logs (optional)
read -p "Remove log files? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf /var/log/vkm
fi

echo "VKM uninstalled successfully"
EOF
    
    chmod +x "$INSTALL_DIR/uninstall.sh"
    log_success "Uninstaller created at $INSTALL_DIR/uninstall.sh"
}

# Main installation function
main() {
    show_banner
    
    log_info "Starting VKM installation..."
    
    check_root
    detect_distribution
    check_requirements
    install_dependencies
    install_vkm
    create_service
    setup_completion
    configure_firewall
    initial_optimization
    setup_logging
    create_uninstaller
    
    log_success "Installation completed successfully!"
    echo
    echo -e "${GREEN}VPS Kernel Manager is now installed${NC}"
    echo -e "${BLUE}Usage:${NC}"
    echo "  vkm interactive    - Start interactive mode"
    echo "  vkm info          - Show system information"
    echo "  vkm list-kernels  - List available kernels"
    echo "  vkm optimize      - Apply VPS optimizations"
    echo "  vkm benchmark     - Run performance benchmark"
    echo "  vkm --help        - Show all commands"
    echo
    echo -e "${YELLOW}Quick start:${NC}"
    echo "  sudo vkm interactive"
    echo
    echo -e "${BLUE}Documentation:${NC} Run 'vkm --help' for detailed usage"
    echo -e "${BLUE}Logs:${NC} /var/log/vkm/"
    echo -e "${BLUE}Config:${NC} /etc/vkm/vkm.conf"
    echo -e "${BLUE}Uninstall:${NC} $INSTALL_DIR/uninstall.sh"
}

# Trap errors
trap 'log_error "Installation failed at line $LINENO"' ERR

# Run main function
main "$@"
