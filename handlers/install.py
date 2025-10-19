"""
Handler instalasi Windows
Unified installation flow untuk Telegram dan API
Port RDP otomatis 22, cross-platform notifications
"""

import logging
import asyncio
from typing import Dict, Any, Tuple, Optional
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import Settings
from database.users import UserDatabase
from database.installations import InstallationDatabase
from core.ssh_manager import SSHManager
from utils.messages import Messages
from utils.helpers import (
    handle_errors, require_login, Validators,
    NotificationService, InstallationProgressManager
)

logger = logging.getLogger(__name__)


class InstallHandler:
    """Handler untuk instalasi Windows dengan unified flow"""
    
    def __init__(self, user_db: UserDatabase, install_db: InstallationDatabase):
        self.user_db = user_db
        self.install_db = install_db
        self.active_installations: Dict[str, asyncio.Task] = {}
        self.notification_service = NotificationService()
        self.notification_service.set_databases(user_db, install_db)
        self.progress_manager = InstallationProgressManager()
    
    @handle_errors
    @require_login
    async def install(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /install"""
        telegram_id = update.effective_user.id
        
        # Ambil user data
        user_data = await self.user_db.get_user_by_telegram_id(telegram_id)
        if not user_data:
            await update.message.reply_text("User data not found. Please login again.")
            return
        
        username, user_info = user_data
        user_id = user_info.get('id')
        
        if not user_id:
            await update.message.reply_text("User ID not found. Please login again.")
            return
        
        # Cek argumen - 4 parameter
        if not context.args or len(context.args) != 4:
            await update.message.reply_text(Messages.INSTALL_USAGE)
            return
        
        ip, vps_pass, os_code, rdp_pass = context.args
        
        # Validasi input
        if not Validators.validate_ip(ip):
            await update.message.reply_text(Messages.ERROR_INVALID_IP)
            return
        
        if not Validators.validate_rdp_password(rdp_pass):
            await update.message.reply_text(Messages.ERROR_INVALID_PASSWORD)
            return
        
        if not Validators.validate_os_code(os_code):
            await update.message.reply_text(Messages.ERROR_INVALID_OS)
            return
        
        # Dapatkan informasi OS
        os_info = Settings.WINDOWS_OS[os_code]
        
        # Kirim pesan awal
        msg = await update.message.reply_text(Messages.INSTALL_STEP_CONNECTING.format(ip=ip))
        
        # Buat task untuk instalasi
        task = asyncio.create_task(
            self.process_installation(
                user_id=user_id,
                install_data={
                    'ip': ip,
                    'vps_password': vps_pass,
                    'os_code': os_code,
                    'os_name': os_info['name'],
                    'rdp_password': rdp_pass,
                    'boot_mode': 'unknown'
                },
                source="telegram",
                telegram_message=msg
            )
        )
        
        # Simpan task
        task_id = f"{telegram_id}_{ip}"
        self.active_installations[task_id] = task
    
    async def process_installation(
        self,
        user_id: int,
        install_data: Dict[str, Any],
        source: str = "telegram",
        telegram_message=None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Core installation process dengan single message updates
        """
        install_id = None
        ssh = None
        result_data = {
            'status': Settings.INSTALL_STATUS_FAILED,
            'error': None,
            'rdp_info': None,
            'boot_mode': 'unknown'
        }
        
        try:
            # Extract installation data
            ip = install_data['ip']
            vps_password = install_data['vps_password']
            os_code = install_data['os_code']
            os_name = install_data['os_name']
            rdp_password = install_data['rdp_password']
            
            # Create installation record
            install_id = await self.install_db.create_installation(user_id, install_data)
            if not install_id:
                error_msg = "Failed to create installation record"
                if telegram_message:
                    await self.progress_manager.send_final_message(
                        telegram_message,
                        Messages.INSTALL_FAILED_RESULT.format(ip=ip, error=error_msg)
                    )
                result_data['error'] = error_msg
                return Settings.INSTALL_STATUS_FAILED, result_data
            
            # Send start notification
            await self.notification_service.notify_installation_started(
                user_id, install_id, ip, os_name, source
            )
            
            # Initialize SSH Manager
            ssh = SSHManager()
            
            # STEP 1: CONNECTING (message already sent)
            await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_CONNECTING)
            await self.install_db.update_step(install_id, f"Connecting to {ip}")
            
            success, error = await ssh.connect(ip, vps_password)
            if not success:
                # Format error message
                error_msg = Messages.INSTALL_ERROR_CONNECTION.format(error=error)
                
                # Send final error message
                if telegram_message:
                    await self.progress_manager.send_final_message(
                        telegram_message,
                        Messages.INSTALL_FAILED_RESULT.format(ip=ip, error=error_msg)
                    )
                
                await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_FAILED, {'error': error})
                await self.user_db.update_install_stats(user_id, False)
                await self.notification_service.notify_installation_failed(user_id, install_id, ip, error, source)
                
                result_data['error'] = error
                return Settings.INSTALL_STATUS_FAILED, result_data
            
            # STEP 2: CONNECTED
            if telegram_message:
                await self.progress_manager.update_message(
                    telegram_message,
                    Messages.INSTALL_STEP_CONNECTED.format(ip=ip),
                    delay=1.0
                )
            
            # STEP 3: CHECKING SYSTEM
            if telegram_message:
                await self.progress_manager.update_message(
                    telegram_message,
                    Messages.INSTALL_STEP_CHECKING
                )
            
            await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_CHECKING)
            await self.install_db.update_step(install_id, "Checking system specifications")
            
            specs = await ssh.check_system_specs(ip)
            
            # Validasi spesifikasi
            if specs['ram_mb'] < Settings.MIN_RAM_MB:
                error_msg = Messages.INSTALL_ERROR_RAM.format(
                    available=round(specs['ram_mb']/1024, 1),
                    required=Settings.MIN_RAM_MB/1024
                )
                if telegram_message:
                    await self.progress_manager.send_final_message(
                        telegram_message,
                        Messages.INSTALL_FAILED_RESULT.format(ip=ip, error=error_msg)
                    )
                
                await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_FAILED, {'error': "Insufficient RAM"})
                await self.user_db.update_install_stats(user_id, False)
                await self.notification_service.notify_installation_failed(user_id, install_id, ip, "Insufficient RAM", source)
                
                result_data['error'] = "Insufficient RAM"
                return Settings.INSTALL_STATUS_FAILED, result_data
            
            if specs['disk_gb'] < Settings.MIN_DISK_GB:
                error_msg = Messages.INSTALL_ERROR_DISK.format(
                    available=specs['disk_gb'],
                    required=Settings.MIN_DISK_GB
                )
                if telegram_message:
                    await self.progress_manager.send_final_message(
                        telegram_message,
                        Messages.INSTALL_FAILED_RESULT.format(ip=ip, error=error_msg)
                    )
                
                await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_FAILED, {'error': "Insufficient disk"})
                await self.user_db.update_install_stats(user_id, False)
                await self.notification_service.notify_installation_failed(user_id, install_id, ip, "Insufficient disk", source)
                
                result_data['error'] = "Insufficient disk"
                return Settings.INSTALL_STATUS_FAILED, result_data
            
            if specs['os_type'] not in Settings.SUPPORTED_OS_TYPES:
                error_msg = Messages.INSTALL_ERROR_OS.format(os_type=specs['os_type'])
                if telegram_message:
                    await self.progress_manager.send_final_message(
                        telegram_message,
                        Messages.INSTALL_FAILED_RESULT.format(ip=ip, error=error_msg)
                    )
                
                await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_FAILED, {'error': "Unsupported OS"})
                await self.user_db.update_install_stats(user_id, False)
                await self.notification_service.notify_installation_failed(user_id, install_id, ip, "Unsupported OS", source)
                
                result_data['error'] = "Unsupported OS"
                return Settings.INSTALL_STATUS_FAILED, result_data
            
            boot_mode = specs['boot_mode']
            result_data['boot_mode'] = boot_mode
            
            # STEP 4: SYSTEM CHECK PASSED
            if telegram_message:
                await self.progress_manager.update_message(
                    telegram_message,
                    Messages.INSTALL_STEP_CHECKED,
                    delay=1.0
                )
            
            # STEP 5: PREPARING
            if telegram_message:
                await self.progress_manager.update_message(
                    telegram_message,
                    Messages.INSTALL_STEP_PREPARING
                )
            
            await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_PREPARING)
            await self.install_db.update_step(install_id, "Preparing installation")
            await self.notification_service.notify_installation_progress(user_id, install_id, ip, "Preparing", source)
            
            success, error = await ssh.prepare_installation(ip)
            if not success:
                error_msg = Messages.INSTALL_ERROR_PREPARATION.format(error=error)
                if telegram_message:
                    await self.progress_manager.send_final_message(
                        telegram_message,
                        Messages.INSTALL_FAILED_RESULT.format(ip=ip, error=error_msg)
                    )
                
                await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_FAILED, {'error': error})
                await self.user_db.update_install_stats(user_id, False)
                await self.notification_service.notify_installation_failed(user_id, install_id, ip, error, source)
                
                result_data['error'] = error
                return Settings.INSTALL_STATUS_FAILED, result_data
            
            # STEP 6: PREPARED
            if telegram_message:
                await self.progress_manager.update_message(
                    telegram_message,
                    Messages.INSTALL_STEP_PREPARED,
                    delay=1.0
                )
            
            # STEP 7: INSTALLING
            if telegram_message:
                await self.progress_manager.update_message(
                    telegram_message,
                    Messages.INSTALL_STEP_INSTALLING.format(ip=ip)
                )
            
            await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_INSTALLING)
            await self.install_db.update_step(install_id, "Installing Windows")
            await self.notification_service.notify_installation_progress(user_id, install_id, ip, "Installing Windows", source)
            
            success, message = await ssh.start_installation(ip, os_code, rdp_password, boot_mode)
            if not success:
                error_msg = Messages.INSTALL_ERROR_GENERIC.format(error=message)
                if telegram_message:
                    await self.progress_manager.send_final_message(
                        telegram_message,
                        Messages.INSTALL_FAILED_RESULT.format(ip=ip, error=error_msg)
                    )
                
                await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_FAILED, {'error': message})
                await self.user_db.update_install_stats(user_id, False)
                await self.notification_service.notify_installation_failed(user_id, install_id, ip, message, source)
                
                result_data['error'] = message
                return Settings.INSTALL_STATUS_FAILED, result_data
            
            # STEP 8: MONITORING
            if telegram_message:
                await self.progress_manager.update_message(
                    telegram_message,
                    Messages.INSTALL_STEP_MONITORING.format(ip=ip)
                )
            
            await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_MONITORING)
            await self.install_db.update_step(install_id, f"Monitoring installation on port {Settings.MONITORING_PORT}")
            await self.notification_service.notify_installation_progress(user_id, install_id, ip, "Monitoring progress", source)
            
            # Wait before monitoring
            await asyncio.sleep(Settings.TIMEOUT_MONITORING_START)
            
            # Monitor installation
            installation_complete = False
            monitoring_start = asyncio.get_event_loop().time()
            max_monitoring_time = Settings.TIMEOUT_INSTALLATION - Settings.TIMEOUT_MONITORING_START
            consecutive_closed_count = 0
            required_consecutive_checks = Settings.TIMEOUT_MONITORING_CHECKS
            
            while True:
                current_time = asyncio.get_event_loop().time()
                if current_time - monitoring_start > max_monitoring_time:
                    # TIMEOUT
                    if telegram_message:
                        await self.progress_manager.send_final_message(
                            telegram_message,
                            Messages.INSTALL_TIMEOUT_RESULT.format(
                                ip=ip,
                                port=Settings.RDP_PORT,
                                password=rdp_password
                            )
                        )
                    
                    await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_TIMEOUT)
                    await self.user_db.update_install_stats(user_id, False)
                    await self.notification_service.notify_installation_timeout(user_id, install_id, ip, source)
                    
                    result_data['status'] = Settings.INSTALL_STATUS_TIMEOUT
                    result_data['rdp_info'] = {
                        'ip': ip,
                        'port': Settings.RDP_PORT,
                        'username': 'Administrator',
                        'password': rdp_password
                    }
                    return Settings.INSTALL_STATUS_TIMEOUT, result_data
                
                # Check monitoring port
                port_open = await ssh.check_port(ip, Settings.MONITORING_PORT, timeout=5)
                
                if not port_open:
                    consecutive_closed_count += 1
                    logger.info(f"Port {Settings.MONITORING_PORT} closed, check {consecutive_closed_count}/{required_consecutive_checks} for {ip}")
                    
                    if consecutive_closed_count >= required_consecutive_checks:
                        installation_complete = True
                        break
                else:
                    consecutive_closed_count = 0
                
                await asyncio.sleep(Settings.TIMEOUT_MONITORING_INTERVAL)
            
            if installation_complete:
                # SUCCESS
                if telegram_message:
                    await self.progress_manager.send_final_message(
                        telegram_message,
                        Messages.INSTALL_SUCCESS_RESULT.format(
                            ip=ip,
                            port=Settings.RDP_PORT,
                            password=rdp_password
                        )
                    )
                
                rdp_info = {
                    'ip': ip,
                    'port': Settings.RDP_PORT,
                    'username': 'Administrator',
                    'password': rdp_password
                }
                
                await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_COMPLETED, {
                    'rdp_info': rdp_info,
                    'boot_mode': boot_mode
                })
                await self.user_db.update_install_stats(user_id, True)
                await self.notification_service.notify_installation_completed(user_id, install_id, ip, rdp_password, source)
                
                result_data['status'] = Settings.INSTALL_STATUS_COMPLETED
                result_data['rdp_info'] = rdp_info
                return Settings.INSTALL_STATUS_COMPLETED, result_data
                
        except Exception as e:
            logger.error(f"Installation error: {e}", exc_info=True)
            error_msg = Messages.INSTALL_ERROR_GENERIC.format(error=str(e))
            
            if telegram_message:
                try:
                    await self.progress_manager.send_final_message(
                        telegram_message,
                        Messages.INSTALL_FAILED_RESULT.format(ip=ip, error=str(e))
                    )
                except:
                    pass
            
            if install_id:
                await self.install_db.update_status(install_id, Settings.INSTALL_STATUS_FAILED, {'error': str(e)})
            
            await self.user_db.update_install_stats(user_id, False)
            await self.notification_service.notify_installation_failed(user_id, install_id, ip, str(e), source)
            
            result_data['error'] = str(e)
            return Settings.INSTALL_STATUS_FAILED, result_data
            
        finally:
            if ssh:
                await ssh.cleanup()
            
            # Remove task from active installations if from Telegram
            if source == "telegram" and telegram_message:
                try:
                    telegram_id = telegram_message.chat_id
                    task_id = f"{telegram_id}_{ip}"
                    if task_id in self.active_installations:
                        del self.active_installations[task_id]
                except:
                    pass
    
    @handle_errors
    async def oslist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /oslist"""
        servers = []
        desktops = []
        
        for code, info in Settings.WINDOWS_OS.items():
            line = f"{code} - {info['name']}"
            if info.get('category') == 'server':
                servers.append(line)
            else:
                desktops.append(line)
        
        message = Messages.OS_LIST.format(
            servers='\n'.join([f"- {s}" for s in servers]),
            desktops='\n'.join([f"- {d}" for d in desktops])
        )
        
        await update.message.reply_text(message)
    
    @handle_errors
    @require_login
    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /history"""
        telegram_id = update.effective_user.id
        
        user_data = await self.user_db.get_user_by_telegram_id(telegram_id)
        if not user_data:
            await update.message.reply_text(Messages.USER_NOT_FOUND)
            return
        
        username, user_info = user_data
        user_id = user_info.get('id')
        
        if not user_id:
            await update.message.reply_text("User ID not found. Please login again.")
            return
        
        installations = await self.install_db.get_user_installations(user_id)
        
        if not installations:
            await update.message.reply_text(Messages.NO_INSTALLATION_HISTORY)
            return
        
        message_lines = [Messages.INSTALLATION_HISTORY_HEADER]
        
        for install in installations[:10]:
            status_text = {
                Settings.INSTALL_STATUS_COMPLETED: "[COMPLETED]",
                Settings.INSTALL_STATUS_FAILED: "[FAILED]", 
                Settings.INSTALL_STATUS_TIMEOUT: "[TIMEOUT]"
            }.get(install['status'], "[IN PROGRESS]")
            
            date = install['start_time'][:10] if install['start_time'] else 'Unknown'
            message_lines.append(f"{status_text} {install['os_name']}")
            message_lines.append(f"   IP: {install['ip']}")
            message_lines.append(f"   Date: {date}")
            
            if install['status'] == Settings.INSTALL_STATUS_COMPLETED and install.get('rdp_info'):
                message_lines.append(f"   RDP Port: {Settings.RDP_PORT}")
            
            message_lines.append("")
        
        await update.message.reply_text('\n'.join(message_lines))