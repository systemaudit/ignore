"""
Handler admin untuk command administratif
Menangani user management, broadcast, monitoring sistem, dan database management
"""

import logging
import asyncio
import psutil
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import Settings
from database.users import UserDatabase
from database.installations import InstallationDatabase
from database.connection import db_manager
from utils.messages import Messages
from utils.helpers import handle_errors, require_admin, chunk_message

logger = logging.getLogger(__name__)


class AdminHandler:
    """Handler untuk admin commands"""
    
    def __init__(self, user_db: UserDatabase, install_db: InstallationDatabase):
        self.user_db = user_db
        self.install_db = install_db
    
    @handle_errors
    @require_admin
    async def adminpanel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /adminpanel"""
        try:
            # System statistics
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Database statistics
            install_stats = await self.install_db.get_stats()
            user_stats = await self.user_db.get_user_stats()
            
            # Format message
            message = Messages.ADMIN_MENU.format(
                cpu=cpu,
                ram_percent=mem.percent,
                ram_used=round(mem.used/1024/1024/1024, 1),
                ram_total=round(mem.total/1024/1024/1024, 1),
                disk_percent=disk.percent,
                disk_used=round(disk.used/1024/1024/1024, 1),
                disk_total=round(disk.total/1024/1024/1024, 1),
                active=install_stats.get('active', 0),
                total=install_stats.get('total', 0),
                completed=install_stats.get('completed', 0),
                failed=install_stats.get('failed', 0)
            )
            
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in adminpanel: {e}")
            await update.message.reply_text(Messages.ADMIN_STATS_ERROR)
    
    @handle_errors
    @require_admin
    async def userlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /userlist"""
        try:
            users = await self.user_db.get_user_list()
            
            if not users:
                await update.message.reply_text(Messages.NO_USERS_FOUND)
                return
            
            # Format user list
            message_lines = [Messages.USER_LIST_HEADER]
            
            for user in users[:20]:  # Limit 20 users per message
                status_text = "Admin" if user['is_admin'] else "User"
                if user['status'] != 'active':
                    status_text += f" ({user['status']})"
                
                # Format dates
                created = user['created_at']
                if isinstance(created, str):
                    try:
                        created_date = datetime.fromisoformat(created)
                        created = created_date.strftime('%Y-%m-%d')
                    except:
                        created = created[:10] if len(created) >= 10 else created
                
                last_login = user['last_login']
                if last_login and last_login != 'Never':
                    if isinstance(last_login, str):
                        try:
                            login_date = datetime.fromisoformat(last_login)
                            last_login = login_date.strftime('%m-%d %H:%M')
                        except:
                            last_login = last_login[:16] if len(last_login) >= 16 else last_login
                
                message_lines.append(f"Username: {user['username']}")
                message_lines.append(f"Status: {status_text}")
                message_lines.append(f"Total: {user['total_installs']}")
                message_lines.append(f"Success: {user['success_installs']}")
                message_lines.append(f"Failed: {user['failed_installs']}")
                message_lines.append(f"Created: {created}")
                message_lines.append(f"Login: {last_login}")
                message_lines.append(f"Telegram: {'Yes' if user.get('telegram_id') else 'No'}")
                message_lines.append("---")
            
            if len(users) > 20:
                message_lines.append(f"\n... and {len(users) - 20} more users")
                message_lines.append("Use /dbstats for complete statistics")
            
            message = '\n'.join(message_lines)
            
            # Send in chunks if too long
            chunks = chunk_message(message, 4000)
            for chunk in chunks:
                await update.message.reply_text(chunk)
                
        except Exception as e:
            logger.error(f"Error in userlist: {e}")
            await update.message.reply_text("Error retrieving user list")
    
    @handle_errors
    @require_admin
    async def adduser(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /adduser"""
        try:
            if not context.args or len(context.args) != 2:
                await update.message.reply_text(Messages.ADDUSER_FORMAT)
                return
            
            username, password = context.args
            
            # Add user without telegram_id (for manual addition)
            success, reason = await self.user_db.add_user(username, password)
            
            if success:
                await update.message.reply_text(
                    Messages.USER_ADDED.format(username=username)
                )
            else:
                await update.message.reply_text(
                    Messages.USER_ADD_FAILED.format(reason=reason)
                )
                
        except Exception as e:
            logger.error(f"Error in adduser: {e}")
            await update.message.reply_text("Error adding user")
    
    @handle_errors
    @require_admin
    async def deleteuser(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /deleteuser"""
        try:
            if not context.args or len(context.args) != 1:
                await update.message.reply_text(Messages.DELETEUSER_FORMAT)
                return
            
            username = context.args[0]
            
            success, reason = await self.user_db.delete_user(username)
            
            if success:
                await update.message.reply_text(
                    Messages.USER_DELETED.format(username=username)
                )
            else:
                await update.message.reply_text(
                    Messages.USER_DELETE_FAILED.format(reason=reason)
                )
                
        except Exception as e:
            logger.error(f"Error in deleteuser: {e}")
            await update.message.reply_text("Error deleting user")
    
    @handle_errors
    @require_admin
    async def banuser(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /banuser"""
        try:
            if not context.args or len(context.args) != 1:
                await update.message.reply_text(Messages.BANUSER_FORMAT)
                return
            
            username = context.args[0]
            
            success, reason = await self.user_db.ban_user(username)
            
            if success:
                await update.message.reply_text(Messages.USER_BANNED.format(username=username))
            else:
                await update.message.reply_text(Messages.USER_BAN_FAILED.format(reason=reason))
                
        except Exception as e:
            logger.error(f"Error in banuser: {e}")
            await update.message.reply_text("Error banning user")
    
    @handle_errors
    @require_admin
    async def unbanuser(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /unbanuser"""
        try:
            if not context.args or len(context.args) != 1:
                await update.message.reply_text(Messages.UNBANUSER_FORMAT)
                return
            
            username = context.args[0]
            
            success, reason = await self.user_db.unban_user(username)
            
            if success:
                await update.message.reply_text(Messages.USER_UNBANNED.format(username=username))
            else:
                await update.message.reply_text(Messages.USER_UNBAN_FAILED.format(reason=reason))
                
        except Exception as e:
            logger.error(f"Error in unbanuser: {e}")
            await update.message.reply_text("Error unbanning user")
    
    @handle_errors
    @require_admin
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /broadcast"""
        try:
            if not context.args:
                await update.message.reply_text(Messages.BROADCAST_FORMAT)
                return
            
            message = ' '.join(context.args)
            
            # Get all active telegram IDs
            telegram_ids = await self.user_db.get_all_telegram_ids()
            
            if not telegram_ids:
                await update.message.reply_text(Messages.NO_ACTIVE_USERS)
                return
            
            # Send broadcast
            success_count = 0
            failed_count = 0
            
            broadcast_message = Messages.BROADCAST_MESSAGE.format(message=message)
            
            for telegram_id in telegram_ids:
                try:
                    await context.bot.send_message(telegram_id, broadcast_message)
                    success_count += 1
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.warning(f"Failed to send broadcast to {telegram_id}: {e}")
                    failed_count += 1
            
            await update.message.reply_text(
                Messages.BROADCAST_SENT.format(
                    success=success_count,
                    failed=failed_count,
                    total=len(telegram_ids)
                )
            )
            
        except Exception as e:
            logger.error(f"Error in broadcast: {e}")
            await update.message.reply_text("Error sending broadcast")
    
    @handle_errors
    @require_admin
    async def cleanup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /cleanup"""
        try:
            # Cleanup stuck installations
            stuck = await self.install_db.cleanup_stuck_installations()
            
            # Cleanup old installations
            old = await self.install_db.cleanup_old_installations()
            
            # Cleanup expired sessions
            await self.user_db._cleanup_expired_sessions()
            
            total = stuck + old
            
            await update.message.reply_text(
                Messages.CLEANUP_DONE.format(
                    stuck=stuck,
                    old=old,
                    total=total
                )
            )
            
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")
            await update.message.reply_text("Error performing cleanup")
    
    @handle_errors
    @require_admin
    async def dbstatus(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /dbstatus"""
        try:
            # Database connection status
            connection_status = await db_manager.get_connection_status()
            
            # Database info
            db_info = await db_manager.get_database_info()
            
            status_text = "Active" if connection_status.get('status') == 'active' else "Disconnected"
            
            message = Messages.DB_STATUS_HEADER.format(
                status=status_text,
                active=connection_status.get('used', 0),
                max=connection_status.get('maxsize', 0),
                size=round(db_info.get('database_size_mb', 0), 1)
            )
            
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in dbstatus: {e}")
            await update.message.reply_text("Error retrieving database status")
    
    @handle_errors
    @require_admin
    async def dbstats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /dbstats"""
        try:
            # Installation statistics
            install_stats = await self.install_db.get_stats()
            
            # User statistics
            user_stats = await self.user_db.get_user_stats()
            
            message = Messages.DB_STATS_HEADER.format(
                users=user_stats.get('total_users', 0),
                installations=install_stats.get('total', 0),
                rate=install_stats.get('success_rate', 0)
            )
            
            # Add OS statistics
            os_stats = install_stats.get('os_stats', {})
            if os_stats:
                message += "\n\nTop OS Installations:"
                top_os = sorted(os_stats.items(), key=lambda x: x[1], reverse=True)[:5]
                for os_code, count in top_os:
                    os_name = Settings.WINDOWS_OS.get(os_code, {}).get('name', os_code)
                    message += f"\n- {os_name}: {count}"
            
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in dbstats: {e}")
            await update.message.reply_text("Error retrieving database statistics")
    
    @handle_errors
    @require_admin
    async def logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk command /logs"""
        try:
            log_file = Settings.LOG_FILE
            
            if not log_file.exists():
                await update.message.reply_text(Messages.LOG_FILE_NOT_FOUND)
                return
            
            # Read last 50 lines
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-50:] if len(lines) > 50 else lines
            
            log_text = ''.join(last_lines)
            
            # Truncate if too long
            if len(log_text) > 3800:
                log_text = "...\n" + log_text[-3800:]
            
            message = Messages.LOG_CONTENT.format(content=log_text)
            
            # Use monospace formatting for logs
            await update.message.reply_text(f"```\n{log_text}\n```", parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in logs: {e}")
            await update.message.reply_text(Messages.LOG_READ_ERROR)