"""
Windows Installer Bot
Bot Telegram untuk instalasi Windows otomatis ke VPS
"""

import logging
import asyncio
import sys
import signal
from pathlib import Path

# Import nest_asyncio untuk fix event loop issues
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "nest_asyncio"], capture_output=True)
    import nest_asyncio
    nest_asyncio.apply()

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config.settings import Settings, validate_environment
from database.connection import init_database, close_database, db_manager
from database.users import UserDatabase
from database.installations import InstallationDatabase
from handlers.auth import AuthHandler
from handlers.install import InstallHandler
from handlers.menu import MenuHandler
from handlers.admin import AdminHandler
from utils.messages import Messages
from utils.helpers import NotificationService

# Konfigurasi logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, Settings.LOG_LEVEL, logging.INFO),
    handlers=[
        logging.FileHandler(Settings.LOG_FILE),
        logging.StreamHandler()
    ]
)

# Suppress noise dari HTTP libraries
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('aiomysql').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class WindowsInstallerBot:
    """Bot utama untuk instalasi Windows"""
    
    def __init__(self):
        # Validasi konfigurasi
        if not validate_environment():
            raise ValueError("Invalid configuration")
        
        # Database managers
        self.user_db = None
        self.install_db = None
        
        # Handlers
        self.auth_handler = None
        self.install_handler = None
        self.menu_handler = None
        self.admin_handler = None
        
        # Notification service
        self.notification_service = None
        
        # Create bot application
        self.app = Application.builder().token(Settings.BOT_TOKEN).build()
        
        # Status flags
        self.is_initialized = False
        self.is_running = False
        
        logger.info(f"Bot initialized: {Settings.BOT_NAME} v{Settings.BOT_VERSION}")
        logger.info(f"Environment: {Settings.ENVIRONMENT}")
        logger.info(f"MySQL Host: {Settings.DB_CONFIG['host']}:{Settings.DB_CONFIG['port']}")
    
    async def initialize_database(self) -> bool:
        """Inisialisasi koneksi database"""
        try:
            logger.info("Connecting to MySQL database...")
            
            # Initialize database connection
            success = await init_database()
            if not success:
                logger.error("Failed to connect to database")
                return False
            
            # Initialize database managers
            self.user_db = UserDatabase()
            await self.user_db.initialize()
            
            self.install_db = InstallationDatabase()
            await self.install_db.initialize()
            
            # Log database status
            db_status = await db_manager.get_connection_status()
            logger.info(f"Database connection pool: {db_status}")
            
            logger.info("Database connected successfully")
            return True
            
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            return False
    
    def initialize_handlers(self):
        """Inisialisasi handlers setelah database ready"""
        try:
            self.auth_handler = AuthHandler(self.user_db)
            self.install_handler = InstallHandler(self.user_db, self.install_db)
            self.menu_handler = MenuHandler(self.user_db, self.install_db)
            self.admin_handler = AdminHandler(self.user_db, self.install_db)
            
            # Setup notification service dengan bot instance
            self.notification_service = NotificationService(self.app.bot)
            self.notification_service.set_databases(self.user_db, self.install_db)
            self.install_handler.notification_service = self.notification_service
            
            logger.info("Handlers initialized successfully")
            
        except Exception as e:
            logger.error(f"Handler initialization error: {e}")
            raise
    
    def setup_handlers(self):
        """Setup semua command handlers"""
        
        if not all([self.auth_handler, self.install_handler, self.menu_handler, self.admin_handler]):
            raise RuntimeError("Handlers not initialized")
        
        # Auth commands
        self.app.add_handler(CommandHandler('start', self.auth_handler.start))
        self.app.add_handler(CommandHandler('login', self.auth_handler.login))
        self.app.add_handler(CommandHandler('register', self.auth_handler.register))
        self.app.add_handler(CommandHandler('logout', self.auth_handler.logout))
        
        # Install commands
        self.app.add_handler(CommandHandler('install', self.install_handler.install))
        self.app.add_handler(CommandHandler('oslist', self.install_handler.oslist))
        self.app.add_handler(CommandHandler('history', self.install_handler.history))
        
        # Menu commands
        self.app.add_handler(CommandHandler('menu', self.menu_handler.menu))
        self.app.add_handler(CommandHandler('help', self.menu_handler.help))
        self.app.add_handler(CommandHandler('profile', self.menu_handler.profile))
        
        # Admin commands
        self.app.add_handler(CommandHandler('adminpanel', self.admin_handler.adminpanel))
        self.app.add_handler(CommandHandler('userlist', self.admin_handler.userlist))
        self.app.add_handler(CommandHandler('adduser', self.admin_handler.adduser))
        self.app.add_handler(CommandHandler('deleteuser', self.admin_handler.deleteuser))
        self.app.add_handler(CommandHandler('banuser', self.admin_handler.banuser))
        self.app.add_handler(CommandHandler('unbanuser', self.admin_handler.unbanuser))
        self.app.add_handler(CommandHandler('broadcast', self.admin_handler.broadcast))
        self.app.add_handler(CommandHandler('cleanup', self.admin_handler.cleanup))
        self.app.add_handler(CommandHandler('dbstatus', self.admin_handler.dbstatus))
        self.app.add_handler(CommandHandler('dbstats', self.admin_handler.dbstats))
        self.app.add_handler(CommandHandler('logs', self.admin_handler.logs))
        
        # Error and unknown command handlers
        self.app.add_error_handler(self.error_handler)
        self.app.add_handler(MessageHandler(filters.COMMAND, self.unknown_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        
        logger.info("All handlers registered")
    
    async def error_handler(self, update: Update, context):
        """Handler untuk error"""
        logger.error(f"Update {update} caused error {context.error}", exc_info=True)
        
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(Messages.ERROR_GENERIC)
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
    
    async def unknown_command(self, update: Update, context):
        """Handler untuk command yang tidak dikenali"""
        await update.message.reply_text(Messages.UNKNOWN_COMMAND)
    
    async def handle_text(self, update: Update, context):
        """Handler untuk pesan teks biasa"""
        user_id = update.effective_user.id
        
        # Check if user is logged in
        if not await self.user_db.check_session(user_id):
            await update.message.reply_text(Messages.NOT_LOGGED_IN)
        else:
            await update.message.reply_text(Messages.USE_MENU)
    
    async def startup_tasks(self):
        """Tasks yang dijalankan saat startup"""
        try:
            logger.info("Running startup tasks...")
            
            # Cleanup stuck installations
            if self.install_db:
                await self.install_db.cleanup_stuck_installations()
                await self.install_db.cleanup_old_installations(days=Settings.CLEANUP_OLD_INSTALLS_DAYS)
                
                # Log database status
                try:
                    db_info = await db_manager.get_database_info()
                    logger.info(f"Database contains: Users: {db_info.get('record_counts', {}).get('users', 0)}, "
                              f"Installations: {db_info.get('record_counts', {}).get('installations', 0)}")
                except Exception as e:
                    logger.warning(f"Could not get database status: {e}")
            
            logger.info("Startup tasks completed - Bot ready")
            
        except Exception as e:
            logger.error(f"Startup error: {e}")
            raise
    
    async def shutdown_tasks(self):
        """Tasks yang dijalankan saat shutdown"""
        try:
            logger.info("Running shutdown tasks...")
            await close_database()
            logger.info("Shutdown tasks completed")
            
        except Exception as e:
            logger.error(f"Shutdown error: {e}")
    
    async def periodic_cleanup(self):
        """Periodic cleanup task"""
        try:
            logger.debug("Running periodic cleanup...")
            
            if self.install_db:
                # Cleanup stuck installations
                stuck_count = await self.install_db.cleanup_stuck_installations()
                if stuck_count > 0:
                    logger.info(f"Cleaned up {stuck_count} stuck installations")
                
                # Cleanup old logs
                old_logs = await self.install_db.cleanup_old_logs()
                if old_logs > 0:
                    logger.info(f"Cleaned up {old_logs} old logs")
            
            if self.user_db:
                # Cleanup expired sessions
                await self.user_db._cleanup_expired_sessions()
            
        except Exception as e:
            logger.error(f"Periodic cleanup error: {e}")
    
    async def initialize_bot_async(self):
        """Inisialisasi bot secara async"""
        try:
            logger.info("Starting async initialization...")
            
            # Initialize database
            success = await self.initialize_database()
            if not success:
                raise RuntimeError("Database initialization failed")
            
            # Initialize handlers
            self.initialize_handlers()
            
            # Setup handlers
            self.setup_handlers()
            
            # Run startup tasks
            await self.startup_tasks()
            
            # Set initialized flag
            self.is_initialized = True
            
            logger.info("Bot initialization successful")
            return True
            
        except Exception as e:
            logger.error(f"Initialization error: {e}")
            return False
    
    def run(self):
        """Menjalankan bot"""
        async def run_bot():
            """Main bot runner function"""
            try:
                # Setup signal handlers
                def signal_handler(signum, frame):
                    logger.info(f"Received signal {signum}, stopping bot...")
                    self.is_running = False
                
                signal.signal(signal.SIGINT, signal_handler)
                signal.signal(signal.SIGTERM, signal_handler)
                
                # Initialize bot
                success = await self.initialize_bot_async()
                if not success:
                    logger.error("Bot initialization failed")
                    return False
                
                # Setup periodic cleanup
                try:
                    if hasattr(self.app, 'job_queue') and self.app.job_queue:
                        self.app.job_queue.run_repeating(
                            callback=lambda context: asyncio.create_task(self.periodic_cleanup()),
                            interval=21600,  # 6 hours
                            first=3600       # Start after 1 hour
                        )
                        logger.info("Periodic cleanup scheduled")
                except Exception as e:
                    logger.warning(f"JobQueue setup failed (not critical): {e}")
                
                # Display startup info
                print(f"\n{Settings.BOT_NAME} v{Settings.BOT_VERSION}")
                print(f"Environment: {Settings.ENVIRONMENT}")
                print(f"MySQL: {Settings.DB_CONFIG['host']}:{Settings.DB_CONFIG['port']}")
                print("Bot is running...")
                print("Press Ctrl+C to stop\n")
                
                self.is_running = True
                
                # Initialize and start application
                await self.app.initialize()
                await self.app.start()
                
                logger.info("Bot started successfully, beginning polling...")
                
                # Start polling
                try:
                    await self.app.updater.start_polling(
                        drop_pending_updates=True,
                        allowed_updates=Update.ALL_TYPES,
                        poll_interval=1.0
                    )
                    
                    # Keep running until signal received
                    while self.is_running:
                        await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Polling error: {e}")
                    raise
                
                finally:
                    # Cleanup
                    logger.info("Stopping bot...")
                    
                    try:
                        if self.app.updater.running:
                            await self.app.updater.stop()
                        if self.app.running:
                            await self.app.stop()
                        await self.app.shutdown()
                    except Exception as e:
                        logger.error(f"App shutdown error: {e}")
                    
                    # Cleanup database
                    await self.shutdown_tasks()
                
                return True
                
            except Exception as e:
                logger.error(f"Run bot error: {e}")
                return False
        
        # Main execution
        try:
            logger.info("Starting bot...")
            result = asyncio.run(run_bot())
            
            if result:
                logger.info("Bot stopped successfully")
                return True
            else:
                logger.error("Bot failed to run")
                return False
                
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            print("\nBot stopped.")
            return True
        except Exception as e:
            logger.critical(f"Fatal error: {e}")
            print(f"Error: {e}")
            return False


async def check_prerequisites():
    """Cek prasyarat sebelum menjalankan bot"""
    try:
        # Validate environment
        if not validate_environment():
            print("Error: Invalid environment configuration")
            print("Check your .env file")
            return False
        
        # Test database connection
        logger.info("Testing database connection...")
        success = await init_database()
        if not success:
            print("Error: Cannot connect to MySQL database")
            print(f"Host: {Settings.DB_CONFIG['host']}:{Settings.DB_CONFIG['port']}")
            print(f"Database: {Settings.DB_CONFIG['database']}")
            print(f"User: {Settings.DB_CONFIG['user']}")
            return False
        
        # Close test connection
        await close_database()
        
        logger.info("Prerequisites check passed")
        return True
        
    except Exception as e:
        logger.error(f"Prerequisites check failed: {e}")
        print(f"Error: {e}")
        return False


def main():
    """Entry point utama"""
    try:
        # Check prerequisites
        print("Checking prerequisites...")
        if not asyncio.run(check_prerequisites()):
            print("Prerequisites check failed. Bot cannot start.")
            return 1
        
        print("Prerequisites OK, starting bot...\n")
        
        # Create and run bot
        bot = WindowsInstallerBot()
        
        # Run bot
        success = bot.run()
        
        if success:
            return 0
        else:
            return 1
        
    except KeyboardInterrupt:
        logger.info("Bot startup cancelled by user")
        print("Bot startup cancelled.")
        return 1
    except Exception as e:
        logger.critical(f"Failed to start bot: {e}")
        print(f"Error: {e}")
        print("Check your MySQL database configuration")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)