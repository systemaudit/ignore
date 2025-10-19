"""
SSH Manager untuk koneksi dan operasi VPS
Simplified dengan port 22 hardcoded untuk RDP
"""

import logging
import asyncio
from typing import Optional, Dict, Tuple, Any
import asyncssh

from config.settings import Settings

logger = logging.getLogger(__name__)


class SSHManager:
    """Manager untuk koneksi SSH dan operasi VPS"""
    
    def __init__(self):
        self.connections: Dict[str, asyncssh.SSHClientConnection] = {}
    
    async def connect(self, ip: str, password: str, username: str = 'root') -> Tuple[bool, str]:
        """Buat koneksi SSH ke VPS"""
        try:
            logger.info(f"Connecting to {ip} as {username}")
            
            conn = await asyncio.wait_for(
                asyncssh.connect(
                    ip,
                    username=username,
                    password=password,
                    known_hosts=None,
                    keepalive_interval=30,
                    login_timeout=60
                ),
                timeout=Settings.TIMEOUT_SSH_CONNECT
            )
            
            self.connections[ip] = conn
            logger.info(f"Successfully connected to {ip}")
            return True, "Connected"
            
        except asyncssh.PermissionDenied:
            error_msg = "Authentication failed - incorrect password or username"
            logger.error(f"Permission denied for {ip}")
            return False, error_msg
        except asyncio.TimeoutError:
            error_msg = "Connection timeout - VPS unreachable or SSH port blocked"
            logger.error(f"Connection timeout to {ip}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Connection error: {str(e)}"
            logger.error(f"Failed to connect to {ip}: {error_msg}")
            return False, error_msg
    
    async def disconnect(self, ip: str) -> None:
        """Tutup koneksi SSH"""
        if ip in self.connections:
            try:
                self.connections[ip].close()
                await self.connections[ip].wait_closed()
                del self.connections[ip]
                logger.info(f"Disconnected from {ip}")
            except Exception as e:
                logger.error(f"Error disconnecting from {ip}: {e}")
    
    async def execute(self, ip: str, command: str, timeout: int = None) -> Tuple[bool, str, str]:
        """Eksekusi command di VPS"""
        if ip not in self.connections:
            logger.error(f"Not connected to {ip}")
            return False, "", "Not connected"
        
        if timeout is None:
            timeout = Settings.TIMEOUT_SSH_EXECUTE
        
        try:
            logger.debug(f"Executing on {ip}: {command[:100]}...")
            
            result = await asyncio.wait_for(
                self.connections[ip].run(command, check=False),
                timeout=timeout
            )
            
            stdout = result.stdout if result.stdout else ""
            stderr = result.stderr if result.stderr else ""
            
            logger.debug(f"Command result - Exit: {result.returncode}, Stdout length: {len(stdout)}, Stderr length: {len(stderr)}")
            
            return True, stdout, stderr
            
        except asyncio.TimeoutError:
            logger.error(f"Command timeout on {ip} after {timeout}s")
            return False, "", f"Command timeout after {timeout} seconds"
        except Exception as e:
            logger.error(f"Error executing command on {ip}: {e}")
            return False, "", str(e)
    
    async def detect_boot_mode(self, ip: str) -> str:
        """Deteksi mode boot sistem (UEFI atau Legacy)"""
        if ip not in self.connections:
            logger.error(f"Not connected to {ip} for boot mode check")
            return "legacy"
        
        try:
            success, stdout, stderr = await self.execute(
                ip,
                Settings.SSH_COMMANDS['CHECK_BOOT'],
                timeout=10
            )
            
            if success and stdout:
                boot_mode = stdout.strip().lower()
                if boot_mode in Settings.SUPPORTED_BOOT_MODES:
                    logger.info(f"Boot mode for {ip}: {boot_mode}")
                    return boot_mode
            
            logger.info(f"Defaulting to legacy boot mode for {ip}")
            return 'legacy'
            
        except Exception as e:
            logger.error(f"Error detecting boot mode for {ip}: {e}")
            return 'legacy'
    
    async def check_system_specs(self, ip: str) -> Dict[str, Any]:
        """Cek spesifikasi sistem VPS"""
        specs = {
            'ram_mb': 0,
            'disk_gb': 0,
            'cpu_cores': 0,
            'os_type': 'unknown',
            'boot_mode': 'unknown'
        }
        
        if ip not in self.connections:
            logger.error(f"Not connected to {ip} for system check")
            return specs
        
        try:
            # Cek RAM
            logger.info(f"Checking RAM for {ip}")
            success, stdout, stderr = await self.execute(
                ip,
                Settings.SSH_COMMANDS['CHECK_RAM'],
                timeout=30
            )
            if success and stdout:
                try:
                    ram_value = stdout.strip()
                    specs['ram_mb'] = int(ram_value)
                    logger.info(f"RAM for {ip}: {specs['ram_mb']} MB")
                except ValueError as e:
                    logger.error(f"Failed to parse RAM value '{stdout}': {e}")
            
            # Cek Disk
            logger.info(f"Checking disk for {ip}")
            success, stdout, stderr = await self.execute(
                ip,
                Settings.SSH_COMMANDS['CHECK_DISK'],
                timeout=30
            )
            if success and stdout:
                try:
                    disk_value = stdout.strip()
                    specs['disk_gb'] = int(disk_value)
                    logger.info(f"Disk for {ip}: {specs['disk_gb']} GB")
                except ValueError as e:
                    logger.error(f"Failed to parse disk value '{stdout}': {e}")
            
            # Cek CPU cores
            logger.info(f"Checking CPU cores for {ip}")
            success, stdout, stderr = await self.execute(
                ip,
                Settings.SSH_COMMANDS['CHECK_CPU'],
                timeout=30
            )
            if success and stdout:
                try:
                    specs['cpu_cores'] = int(stdout.strip())
                    logger.info(f"CPU cores for {ip}: {specs['cpu_cores']}")
                except ValueError as e:
                    logger.error(f"Failed to parse CPU cores '{stdout}': {e}")
            
            # Cek OS type
            logger.info(f"Checking OS type for {ip}")
            success, stdout, stderr = await self.execute(
                ip,
                Settings.SSH_COMMANDS['CHECK_OS'],
                timeout=30
            )
            if success and stdout:
                specs['os_type'] = stdout.strip().lower()
                logger.info(f"OS type for {ip}: {specs['os_type']}")
            else:
                # Fallback check
                success, stdout, stderr = await self.execute(
                    ip,
                    Settings.SSH_COMMANDS['CHECK_OS_FALLBACK'],
                    timeout=30
                )
                if success and stdout:
                    specs['os_type'] = stdout.strip().lower()
            
            # Cek boot mode
            logger.info(f"Checking boot mode for {ip}")
            specs['boot_mode'] = await self.detect_boot_mode(ip)
            
            logger.info(f"System specs for {ip}: {specs}")
            return specs
            
        except Exception as e:
            logger.error(f"Error checking specs for {ip}: {e}")
            return specs
    
    async def prepare_installation(self, ip: str) -> Tuple[bool, str]:
        """Persiapan VPS untuk instalasi Windows"""
        if ip not in self.connections:
            return False, "Not connected"
        
        try:
            # Cleanup old installation
            logger.info(f"Cleaning up old installation on {ip}")
            await self.execute(ip, Settings.SSH_COMMANDS['CLEANUP_OLD'], timeout=30)
            
            # Create directory
            logger.info(f"Creating installation directory on {ip}")
            await self.execute(ip, Settings.SSH_COMMANDS['CREATE_DIR'], timeout=30)
            
            # Download installation script
            logger.info(f"Downloading installation script to {ip}")
            download_cmd = Settings.get_ssh_command('DOWNLOAD_SCRIPT')
            success, stdout, stderr = await self.execute(
                ip, 
                download_cmd, 
                timeout=120
            )
            if not success:
                logger.error(f"Download failed: {stderr}")
                return False, f"Failed to download script: {stderr}"
            
            # Verify script exists
            success, stdout, stderr = await self.execute(
                ip,
                Settings.SSH_COMMANDS['VERIFY_SCRIPT'],
                timeout=10
            )
            
            if success and 'OK' in stdout:
                logger.info(f"Installation prepared for {ip}")
                return True, "Ready"
            else:
                return False, "Script verification failed"
                
        except Exception as e:
            error_msg = f"Preparation failed: {str(e)}"
            logger.error(f"Error preparing {ip}: {error_msg}")
            return False, error_msg
    
    async def start_installation(self, ip: str, os_code: str, rdp_password: str, boot_mode: str) -> Tuple[bool, str]:
        """Mulai instalasi Windows dengan port 22 untuk RDP"""
        if ip not in self.connections:
            return False, "Not connected"
        
        try:
            # Dapatkan image URL berdasarkan OS dan boot mode
            image_url = Settings.get_image_url(os_code, boot_mode)
            logger.info(f"Using image URL for {ip}: {image_url} (boot: {boot_mode})")
            
            # Generate install command dengan port 22
            install_cmd = Settings.get_install_command(rdp_password, image_url)
            
            logger.info(f"Starting installation on {ip} with RDP port {Settings.RDP_PORT}")
            
            # Eksekusi command instalasi
            try:
                success, stdout, stderr = await self.execute(
                    ip, 
                    install_cmd,
                    timeout=Settings.TIMEOUT_SSH_LONG
                )
                
                # Cek error yang jelas
                if stderr and ("Error" in stderr or "Failed" in stderr):
                    logger.error(f"Installation error detected: {stderr[:200]}")
                    return False, f"Installation error: {stderr[:200]}"
                
                logger.info(f"Installation command completed for {ip}, scheduling reboot")
                
            except asyncio.TimeoutError:
                # Timeout normal untuk DD mode
                logger.info(f"Installation command timeout (normal for DD mode) for {ip}")
            
            # Schedule reboot
            try:
                await self.execute(
                    ip,
                    Settings.SSH_COMMANDS['SCHEDULE_REBOOT'],
                    timeout=10
                )
                logger.info(f"Reboot scheduled for {ip}")
            except Exception as e:
                logger.warning(f"Failed to schedule reboot (may already be scheduled): {e}")
            
            return True, f"Installation configured successfully. VPS will reboot in 5 seconds. RDP will be available on port {Settings.RDP_PORT}."
            
        except Exception as e:
            error_msg = f"Installation error: {str(e)}"
            logger.error(f"Error installing on {ip}: {error_msg}")
            return False, error_msg
    
    async def check_port(self, ip: str, port: int, timeout: int = 5) -> bool:
        """Cek apakah port terbuka"""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=timeout
            )
            writer.close()
            await writer.wait_closed()
            return True
        except:
            return False
    
    async def check_rdp_availability(self, ip: str, timeout: int = 3) -> bool:
        """Cek apakah RDP sudah tersedia di port 22"""
        return await self.check_port(ip, Settings.RDP_PORT, timeout)
    
    async def cleanup(self) -> None:
        """Tutup semua koneksi"""
        ips = list(self.connections.keys())
        for ip in ips:
            await self.disconnect(ip)