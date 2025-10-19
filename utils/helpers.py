"""
Helper functions, decorators, validators, dan notification service
Konsolidasi semua utility functions
"""

import logging
import re
import asyncio
from functools import wraps
from typing import Optional, Dict, Any
from telegram import Update, Bot
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from config.settings import Settings
from utils.messages import Messages

logger = logging.getLogger(__name__)


# === DECORATORS === #

def handle_errors(func):
    """Decorator untuk handle error secara konsisten"""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(self, update, context)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            try:
                await update.message.reply_text(Messages.ERROR_GENERIC)
            except Exception as reply_error:
                logger.error(f"Failed to send error message: {reply_error}")
    return wrapper


def require_login(func):
    """Decorator untuk memastikan user sudah login"""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not await self.user_db.check_session(user_id):
            await update.message.reply_text(Messages.NOT_LOGGED_IN)
            return
        return await func(self, update, context)
    return wrapper


def require_not_logged_in(func):
    """Decorator untuk memastikan user belum login"""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if await self.user_db.check_session(user_id):
            await update.message.reply_text(Messages.ALREADY_LOGGED_IN)
            return
        return await func(self, update, context)
    return wrapper


def require_admin(func):
    """Decorator untuk memastikan user adalah admin"""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not await self.user_db.check_session(user_id):
            await update.message.reply_text(Messages.NOT_LOGGED_IN)
            return
        if not await self.user_db.is_admin(user_id):
            await update.message.reply_text(Messages.ADMIN_ONLY)
            return
        return await func(self, update, context)
    return wrapper


# === VALIDATORS === #

class Validators:
    """Kumpulan validator functions"""
    
    @staticmethod
    def validate_ip(ip: str) -> bool:
        """Validasi format IP address"""
        pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(pattern, ip):
            return False
        octets = [int(o) for o in ip.split('.')]
        return all(0 <= o <= 255 for o in octets)
    
    @staticmethod
    def validate_rdp_password(password: str) -> bool:
        """Validasi password RDP (min 8 char, upper, lower, number)"""
        if len(password) < Settings.MIN_RDP_PASSWORD_LENGTH:
            return False
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        return has_upper and has_lower and has_digit
    
    @staticmethod
    def validate_username(username: str) -> bool:
        """Validasi username"""
        return (
            len(username) >= Settings.MIN_USERNAME_LENGTH and 
            username.isalnum()
        )
    
    @staticmethod
    def validate_password(password: str) -> bool:
        """Validasi password user biasa"""
        return len(password) >= Settings.MIN_PASSWORD_LENGTH
    
    @staticmethod
    def validate_os_code(os_code: str) -> bool:
        """Validasi OS code"""
        return os_code in Settings.WINDOWS_OS


# === INSTALLATION PROGRESS MANAGER === #

class InstallationProgressManager:
    """Manager untuk handle installation progress messages"""
    
    @staticmethod
    async def update_message(message, text: str, delay: float = 0.3):
        """Update message dengan delay untuk smooth transition"""
        try:
            if message and message.text != text:
                await message.edit_text(text)
                if delay > 0:
                    await asyncio.sleep(delay)
                return True
            return False
        except Exception as e:
            logger.debug(f"Could not update message: {e}")
            return False
    
    @staticmethod
    async def send_final_message(message, text: str, delete_previous: bool = True):
        """Send final message dan hapus yang lama"""
        try:
            if delete_previous and message:
                try:
                    await message.delete()
                except:
                    pass
            
            # Send new message
            if message:
                return await message.chat.send_message(text)
            return None
        except Exception as e:
            logger.error(f"Could not send final message: {e}")
            return None


# === NOTIFICATION SERVICE === #

class NotificationService:
    """Service untuk mengirim notifikasi cross-platform"""
    
    def __init__(self, bot: Bot = None):
        self.bot = bot
        self.user_db = None
        self.install_db = None
    
    def set_databases(self, user_db, install_db):
        """Set database instances"""
        self.user_db = user_db
        self.install_db = install_db
    
    async def notify_installation_started(
        self, 
        user_id: int, 
        install_id: str, 
        ip: str, 
        os_name: str,
        source: str = "telegram"
    ):
        """Notifikasi instalasi dimulai"""
        if source == "api" and self.user_db:
            user = await self.user_db.get_user_by_id(user_id)
            if user and user.get('telegram_id') and self.bot:
                try:
                    message = Messages.NOTIFICATION_INSTALL_STARTED.format(
                        ip=ip,
                        os_name=os_name,
                        install_id=install_id
                    )
                    await self.bot.send_message(user['telegram_id'], message)
                    logger.info(f"Sent start notification to telegram_id {user['telegram_id']}")
                except TelegramError as e:
                    logger.error(f"Failed to send telegram notification: {e}")
    
    async def notify_installation_progress(
        self,
        user_id: int,
        install_id: str,
        ip: str,
        step: str,
        source: str = "telegram"
    ):
        """Notifikasi progress instalasi"""
        if source == "api" and self.user_db:
            user = await self.user_db.get_user_by_id(user_id)
            if user and user.get('telegram_id') and self.bot:
                try:
                    major_steps = [
                        Settings.INSTALL_STATUS_CHECKING,
                        Settings.INSTALL_STATUS_INSTALLING,
                        Settings.INSTALL_STATUS_MONITORING
                    ]
                    
                    if any(s in step.lower() for s in major_steps):
                        message = Messages.NOTIFICATION_INSTALL_PROGRESS.format(
                            ip=ip,
                            step=step
                        )
                        await self.bot.send_message(user['telegram_id'], message)
                        logger.info(f"Sent progress notification to telegram_id {user['telegram_id']}")
                except TelegramError as e:
                    logger.error(f"Failed to send progress notification: {e}")
    
    async def notify_installation_completed(
        self,
        user_id: int,
        install_id: str,
        ip: str,
        rdp_password: str,
        source: str = "telegram"
    ):
        """Notifikasi instalasi selesai"""
        if source == "api" and self.user_db:
            user = await self.user_db.get_user_by_id(user_id)
            if user and user.get('telegram_id') and self.bot:
                try:
                    message = Messages.NOTIFICATION_INSTALL_COMPLETED.format(
                        ip=ip,
                        password=rdp_password
                    )
                    await self.bot.send_message(user['telegram_id'], message)
                    logger.info(f"Sent completion notification to telegram_id {user['telegram_id']}")
                except TelegramError as e:
                    logger.error(f"Failed to send completion notification: {e}")
    
    async def notify_installation_failed(
        self,
        user_id: int,
        install_id: str,
        ip: str,
        error: str,
        source: str = "telegram"
    ):
        """Notifikasi instalasi gagal"""
        if source == "api" and self.user_db:
            user = await self.user_db.get_user_by_id(user_id)
            if user and user.get('telegram_id') and self.bot:
                try:
                    message = Messages.NOTIFICATION_INSTALL_FAILED.format(
                        ip=ip,
                        error=error[:200]
                    )
                    await self.bot.send_message(user['telegram_id'], message)
                    logger.info(f"Sent failure notification to telegram_id {user['telegram_id']}")
                except TelegramError as e:
                    logger.error(f"Failed to send failure notification: {e}")
    
    async def notify_installation_timeout(
        self,
        user_id: int,
        install_id: str,
        ip: str,
        source: str = "telegram"
    ):
        """Notifikasi instalasi timeout"""
        if source == "api" and self.user_db:
            user = await self.user_db.get_user_by_id(user_id)
            if user and user.get('telegram_id') and self.bot:
                try:
                    message = Messages.NOTIFICATION_INSTALL_TIMEOUT.format(ip=ip)
                    await self.bot.send_message(user['telegram_id'], message)
                    logger.info(f"Sent timeout notification to telegram_id {user['telegram_id']}")
                except TelegramError as e:
                    logger.error(f"Failed to send timeout notification: {e}")


# === UTILITY FUNCTIONS === #

async def safe_delete_message(message, delay: int = 0):
    """Safely delete a message with optional delay"""
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        await message.delete()
    except Exception as e:
        logger.debug(f"Could not delete message: {e}")


async def safe_edit_message(message, new_text: str):
    """Safely edit a message"""
    try:
        if message.text != new_text:
            return await message.edit_text(new_text)
        return message
    except Exception as e:
        logger.debug(f"Could not edit message: {e}")
        return message


async def send_or_edit_message(message, new_text: str, delete_old: bool = False):
    """Send new message or edit existing one"""
    try:
        if delete_old and message:
            await message.delete()
            return await message.get_bot().send_message(
                message.chat_id, 
                new_text
            )
        elif message:
            return await safe_edit_message(message, new_text)
    except Exception as e:
        logger.error(f"Failed to send/edit message: {e}")
        return None


def chunk_message(text: str, max_length: int = 4000) -> list:
    """Split long message into chunks"""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    for line in text.split('\n'):
        if len(current_chunk) + len(line) + 1 <= max_length:
            current_chunk += line + '\n'
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = line + '\n'
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks


# === FORMATTER FUNCTIONS === #

def format_size(size_mb: int) -> str:
    """Format ukuran dari MB ke GB jika perlu"""
    if size_mb >= 1024:
        return f"{size_mb / 1024:.1f}GB"
    return f"{size_mb}MB"


def format_installation_status(status: str) -> str:
    """Format status instalasi untuk display"""
    status_map = {
        Settings.INSTALL_STATUS_COMPLETED: "[COMPLETED]",
        Settings.INSTALL_STATUS_FAILED: "[FAILED]",
        Settings.INSTALL_STATUS_TIMEOUT: "[TIMEOUT]",
        Settings.INSTALL_STATUS_MONITORING: "[MONITORING]",
        Settings.INSTALL_STATUS_INSTALLING: "[INSTALLING]"
    }
    return status_map.get(status, "[IN PROGRESS]")


def format_time_elapsed(start_time, end_time=None) -> str:
    """Format waktu yang telah berlalu"""
    if end_time is None:
        end_time = asyncio.get_event_loop().time()
    
    elapsed = end_time - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"