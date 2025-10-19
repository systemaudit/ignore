"""
Handler autentikasi untuk login, register, logout
Support cross-platform dengan auto-link telegram_id
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import Settings
from database.users import UserDatabase
from utils.messages import Messages
from utils.helpers import handle_errors, require_not_logged_in

logger = logging.getLogger(__name__)


class AuthHandler:
    """Handler untuk autentikasi commands"""
    
    def __init__(self, user_db: UserDatabase):
        self.user_db = user_db
    
    @handle_errors
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /start"""
        user_id = update.effective_user.id
        
        # Cek apakah user sudah login
        if await self.user_db.check_session(user_id):
            user_data = await self.user_db.get_user_by_telegram_id(user_id)
            username = user_data[0] if user_data else "User"
            
            await update.message.reply_text(
                Messages.WELCOME_BACK.format(username=username)
            )
        else:
            await update.message.reply_text(Messages.WELCOME)
    
    @handle_errors
    @require_not_logged_in
    async def login(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /login"""
        telegram_id = update.effective_user.id
        
        # Cek argumen
        if not context.args or len(context.args) != 2:
            await update.message.reply_text(Messages.LOGIN_FORMAT)
            return
        
        username, password = context.args
        
        # Verifikasi login dengan telegram_id untuk auto-link
        success, message = await self.user_db.verify_login(username, password, telegram_id)
        
        if success:
            await update.message.reply_text(
                Messages.LOGIN_SUCCESS.format(username=username)
            )
            logger.info(f"User {username} logged in via Telegram {telegram_id}")
        else:
            await update.message.reply_text(
                Messages.LOGIN_FAILED.format(reason=message)
            )
    
    @handle_errors
    @require_not_logged_in
    async def register(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /register"""
        telegram_id = update.effective_user.id
        
        # Cek argumen
        if not context.args or len(context.args) != 3:
            await update.message.reply_text(
                Messages.REGISTER_FORMAT.format(
                    contact=Settings.ADMIN_CONTACT,
                    activation_code=Settings.ACTIVATION_CODE
                )
            )
            return
        
        username, password, activation_code = context.args
        
        # Cek kode aktivasi
        if activation_code != Settings.ACTIVATION_CODE:
            await update.message.reply_text(
                Messages.INVALID_ACTIVATION.format(contact=Settings.ADMIN_CONTACT)
            )
            return
        
        # Cek apakah telegram_id sudah terdaftar
        existing_user = await self.user_db.get_user_by_telegram_id(telegram_id)
        if existing_user:
            await update.message.reply_text(
                f"This Telegram account is already registered as {existing_user[0]}.\n"
                f"Please login with: /login {existing_user[0]} your_password"
            )
            return
        
        # Tambah user baru dengan telegram_id
        success, reason = await self.user_db.add_user(username, password, telegram_id)
        
        if success:
            await update.message.reply_text(
                Messages.REGISTER_SUCCESS.format(
                    username=username,
                    password=password
                )
            )
            logger.info(f"New user {username} registered via Telegram {telegram_id}")
        else:
            await update.message.reply_text(
                Messages.REGISTER_FAILED.format(reason=reason)
            )
    
    @handle_errors
    async def logout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /logout"""
        telegram_id = update.effective_user.id
        
        # Cek apakah user sudah login
        if not await self.user_db.check_session(telegram_id):
            await update.message.reply_text(Messages.NOT_LOGGED_IN)
            return
        
        # Dapatkan username sebelum logout
        user_data = await self.user_db.get_user_by_telegram_id(telegram_id)
        username = user_data[0] if user_data else "User"
        
        # Logout
        success = await self.user_db.logout(telegram_id)
        
        if success:
            await update.message.reply_text(Messages.LOGOUT_SUCCESS)
            logger.info(f"User {username} logged out from Telegram {telegram_id}")
        else:
            await update.message.reply_text(Messages.LOGOUT_FAILED)