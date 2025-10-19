"""
Handler menu dan navigasi
Menangani menu utama, help, dan profile user
"""

import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import Settings
from database.users import UserDatabase
from database.installations import InstallationDatabase
from utils.messages import Messages
from utils.helpers import handle_errors, require_login

logger = logging.getLogger(__name__)


class MenuHandler:
    """Handler untuk menu dan navigasi"""
    
    def __init__(self, user_db: UserDatabase, install_db: InstallationDatabase):
        self.user_db = user_db
        self.install_db = install_db
    
    @handle_errors
    @require_login
    async def menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /menu"""
        telegram_id = update.effective_user.id
        
        # Dapatkan username
        user_data = await self.user_db.get_user_by_telegram_id(telegram_id)
        username = user_data[0] if user_data else "User"
        
        # Cek apakah admin
        is_admin = await self.user_db.is_admin(telegram_id)
        
        # Format menu
        menu_text = Messages.MAIN_MENU.format(
            username=username,
            contact=Settings.ADMIN_CONTACT,
            channel=Settings.SUPPORT_CHANNEL
        )
        
        if is_admin:
            menu_text += Messages.ADMIN_MENU_EXTRA
        
        await update.message.reply_text(menu_text)
    
    @handle_errors
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /help"""
        await update.message.reply_text(
            Messages.HELP_TEXT.format(contact=Settings.ADMIN_CONTACT)
        )
    
    @handle_errors
    @require_login
    async def profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /profile"""
        telegram_id = update.effective_user.id
        
        # Dapatkan data user
        user_data = await self.user_db.get_user_by_telegram_id(telegram_id)
        if not user_data:
            await update.message.reply_text(Messages.USER_NOT_FOUND)
            return
        
        username, data = user_data
        
        # Format tanggal
        created = data.get('created_at', 'Unknown')
        if created != 'Unknown':
            try:
                created_date = datetime.fromisoformat(created)
                created = created_date.strftime('%Y-%m-%d')
            except:
                pass
        
        last_login = data.get('last_login', 'Never')
        if last_login != 'Never':
            try:
                login_date = datetime.fromisoformat(last_login)
                last_login = login_date.strftime('%Y-%m-%d %H:%M')
            except:
                pass
        
        # Hitung success rate
        total = data.get('total_installs', 0)
        success = data.get('success_installs', 0)
        success_rate = (success / total * 100) if total > 0 else 0
        
        # Format pesan profil
        message = Messages.USER_PROFILE.format(
            username=username,
            status='Admin' if data.get('is_admin') else 'User',
            total=total,
            success=success,
            failed=data.get('failed_installs', 0),
            success_rate=success_rate,
            created=created,
            last_login=last_login
        )
        
        await update.message.reply_text(message)