"""
Konfigurasi utama untuk Windows Installer Bot
Menggabungkan semua constants dan configuration
"""

import os
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment
load_dotenv()


class Settings:
    """Konfigurasi utama aplikasi"""
    
    # Bot Information
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    BOT_VERSION = "3.0.0"
    BOT_NAME = "Windows Installer Bot"
    
    # Admin Configuration
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
    ACTIVATION_CODE = os.getenv('ACTIVATION_CODE', 'winux')
    
    # Contact Information
    ADMIN_CONTACT = os.getenv('ADMIN_CONTACT', '@admin')
    SUPPORT_CHANNEL = os.getenv('SUPPORT_CHANNEL', '@channel')
    SUPPORT_GROUP = os.getenv('SUPPORT_GROUP', '@group')
    
    # Directories
    BASE_DIR = Path(__file__).parent.parent
    DATA_DIR = BASE_DIR / 'data'
    LOG_DIR = BASE_DIR / 'logs'
    
    # Buat direktori jika belum ada
    DATA_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    
    # Logging
    LOG_FILE = LOG_DIR / 'bot.log'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')
    
    # Database Configuration
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '3306')),
        'user': os.getenv('DB_USER', 'windows_user'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'windows_installer'),
        'charset': os.getenv('DB_CHARSET', 'utf8mb4'),
        'pool_size': int(os.getenv('DB_POOL_SIZE', '10')),
        'pool_max_overflow': int(os.getenv('DB_POOL_MAX_OVERFLOW', '20')),
        'pool_timeout': int(os.getenv('DB_POOL_TIMEOUT', '30')),
        'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', '3600')),
        'echo': os.getenv('DB_ECHO', 'false').lower() == 'true'
    }
    
    # Database Retry
    DB_RETRY_ATTEMPTS = int(os.getenv('DB_RETRY_ATTEMPTS', '3'))
    DB_RETRY_DELAY = float(os.getenv('DB_RETRY_DELAY', '5'))
    
    # Network Configuration
    RDP_PORT = 22  # Hardcoded karena semua provider buka port 22
    SSH_TIMEOUT = int(os.getenv('SSH_TIMEOUT', '120'))
    INSTALLATION_TIMEOUT = int(os.getenv('INSTALLATION_TIMEOUT', '1800'))  # 30 menit
    
    # User Settings
    SESSION_DURATION_HOURS = 24
    MIN_USERNAME_LENGTH = 3
    MIN_PASSWORD_LENGTH = 6
    MIN_RDP_PASSWORD_LENGTH = 8
    
    # API Configuration
    API_HOST = os.getenv('HOST', '0.0.0.0')
    API_PORT = int(os.getenv('PORT', '8000'))
    API_WORKERS = int(os.getenv('WORKERS', '1'))
    JWT_SECRET = os.getenv('JWT_SECRET', 'change-this-secret-key')
    JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', '24'))
    
    # Installation URLs
    IMAGES_UEFI_URL = "https://winstaller.io/eufi/"
    IMAGES_BIOS_URL = "https://winstaller.io/bios/"
    INSTALL_SCRIPT_URL = "https://kodeazmi.id/windows/reinstall.sh"
    
    # System Requirements
    MIN_RAM_MB = 2048  # 2GB
    MIN_DISK_GB = 30   # 30GB
    SUPPORTED_OS_TYPES = ['ubuntu', 'debian']
    SUPPORTED_BOOT_MODES = ['uefi', 'legacy']
    
    # Timeouts (dalam detik)
    TIMEOUT_SSH_CONNECT = 120
    TIMEOUT_SSH_EXECUTE = 60
    TIMEOUT_SSH_LONG = 180
    TIMEOUT_INSTALLATION = 1800  # 30 menit
    TIMEOUT_MONITORING_START = 360  # 6 menit sebelum mulai monitoring
    TIMEOUT_MONITORING_INTERVAL = 10  # Cek setiap 10 detik
    TIMEOUT_MONITORING_CHECKS = 2  # Cek 2x sebelum confirm selesai
    MONITORING_PORT = 80  # Port untuk monitoring progress
    
    # Cleanup Settings
    CLEANUP_OLD_INSTALLS_DAYS = 7
    CLEANUP_STUCK_HOURS = 24
    CLEANUP_OLD_LOGS_DAYS = 30
    CLEANUP_EXPIRED_SESSIONS_HOURS = 48
    
    # Status Values
    STATUS_ACTIVE = 'active'
    STATUS_BANNED = 'banned'
    STATUS_INACTIVE = 'inactive'
    
    INSTALL_STATUS_STARTING = 'starting'
    INSTALL_STATUS_CONNECTING = 'connecting'
    INSTALL_STATUS_CHECKING = 'checking'
    INSTALL_STATUS_PREPARING = 'preparing'
    INSTALL_STATUS_INSTALLING = 'installing'
    INSTALL_STATUS_MONITORING = 'monitoring'
    INSTALL_STATUS_COMPLETED = 'completed'
    INSTALL_STATUS_FAILED = 'failed'
    INSTALL_STATUS_TIMEOUT = 'timeout'
    
    # Windows OS List
    WINDOWS_OS = {
        'ws2012r2': {
            'name': 'Windows Server 2012 R2',
            'min_ram': '2GB',
            'min_disk': '30GB',
            'category': 'server',
            'image': 'windows2012r2'
        },
        'ws2016': {
            'name': 'Windows Server 2016',
            'min_ram': '2GB',
            'min_disk': '30GB',
            'category': 'server',
            'image': 'windows2016'
        },
        'ws2019': {
            'name': 'Windows Server 2019',
            'min_ram': '2GB',
            'min_disk': '30GB',
            'category': 'server',
            'image': 'windows2019'
        },
        'ws2022': {
            'name': 'Windows Server 2022',
            'min_ram': '2GB',
            'min_disk': '30GB',
            'category': 'server',
            'image': 'windows2022'
        },
        'ws2025': {
            'name': 'Windows Server 2025',
            'min_ram': '2GB',
            'min_disk': '30GB',
            'category': 'server',
            'image': 'windows2025'
        },
        'w10pro': {
            'name': 'Windows 10 Pro',
            'min_ram': '2GB',
            'min_disk': '30GB',
            'category': 'desktop',
            'image': 'windows10'
        },
        'w10atlas': {
            'name': 'Windows 10 Atlas',
            'min_ram': '2GB',
            'min_disk': '30GB',
            'category': 'desktop',
            'image': 'windows10atlas'
        },
        'w11pro': {
            'name': 'Windows 11 Pro',
            'min_ram': '2GB',
            'min_disk': '30GB',
            'category': 'desktop',
            'image': 'windows11'
        },
        'w11atlas': {
            'name': 'Windows 11 Atlas',
            'min_ram': '2GB',
            'min_disk': '30GB',
            'category': 'desktop',
            'image': 'windows11atlas'
        }
    }
    
    # SSH Commands
    SSH_COMMANDS = {
        'CHECK_RAM': "free -m | awk 'NR==2 {print $2}'",
        'CHECK_DISK': "df -BG --output=avail / | tail -n1 | sed 's/G//'",
        'CHECK_CPU': "nproc",
        'CHECK_OS': "grep '^ID=' /etc/os-release | cut -d= -f2 | tr -d '\"'",
        'CHECK_BOOT': "[ -d /sys/firmware/efi ] && echo 'uefi' || echo 'legacy'",
        'CHECK_OS_FALLBACK': "[ -f /etc/debian_version ] && echo 'debian' || echo 'unknown'",
        'CLEANUP_OLD': "rm -rf /root/windows_install",
        'CREATE_DIR': "mkdir -p /root/windows_install",
        'DOWNLOAD_SCRIPT': lambda: f"cd /root/windows_install && wget --timeout=60 --tries=3 -O reinstall.sh {Settings.INSTALL_SCRIPT_URL} && chmod +x reinstall.sh",
        'VERIFY_SCRIPT': "[ -f /root/windows_install/reinstall.sh ] && echo 'OK' || echo 'FAIL'",
        'SCHEDULE_REBOOT': "nohup sh -c 'sleep 5 && reboot' &"
    }
    
    @classmethod
    def get_image_url(cls, os_code: str, boot_mode: str) -> str:
        """Dapatkan URL image berdasarkan OS dan boot mode"""
        os_info = cls.WINDOWS_OS.get(os_code, {})
        image_name = os_info.get('image', 'windows10')
        
        if boot_mode == 'uefi':
            return f"{cls.IMAGES_UEFI_URL}{image_name}.gz"
        else:
            return f"{cls.IMAGES_BIOS_URL}{image_name}.gz"
    
    @classmethod
    def get_install_command(cls, rdp_password: str, image_url: str) -> str:
        """Generate command instalasi dengan port 22"""
        return (
            f"cd /root/windows_install && "
            f"bash reinstall.sh dd "
            f"--rdp-port {cls.RDP_PORT} "
            f"--password '{rdp_password}' "
            f"--img '{image_url}' 2>&1"
        )
    
    @classmethod
    def get_ssh_command(cls, command_key: str) -> str:
        """Get SSH command, handle callable commands"""
        cmd = cls.SSH_COMMANDS.get(command_key)
        if callable(cmd):
            return cmd()
        return cmd
    
    @classmethod
    def get_database_url(cls) -> str:
        """Dapatkan database URL untuk tools"""
        db = cls.DB_CONFIG
        return f"mysql+aiomysql://{db['user']}:{db['password']}@{db['host']}:{db['port']}/{db['database']}?charset={db['charset']}"
    
    @classmethod
    def validate(cls) -> bool:
        """Validasi konfigurasi"""
        errors = []
        
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN not set")
        
        required_db = ['host', 'user', 'password', 'database']
        for field in required_db:
            if not cls.DB_CONFIG.get(field):
                errors.append(f"Database {field} not set")
        
        if not cls.ADMIN_USERNAME or not cls.ADMIN_PASSWORD:
            errors.append("Admin credentials not set")
        
        if errors:
            raise ValueError(f"Configuration invalid: {', '.join(errors)}")
        
        return True


# Helper functions untuk backward compatibility
def validate_environment():
    """Validasi environment saat startup"""
    try:
        Settings.validate()
        return True
    except ValueError as e:
        print(f"Configuration error: {e}")
        return False