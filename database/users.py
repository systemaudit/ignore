"""
Database management untuk users
Simplified dengan single update stats method
Support untuk cross-platform notifications
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List
from database.connection import db_manager
from config.settings import Settings

logger = logging.getLogger(__name__)


class UserDatabase:
    """Database untuk mengelola users"""
    
    def __init__(self):
        self.table_name = 'users'
        self.sessions_table = 'user_sessions'
    
    async def initialize(self):
        """Inisialisasi database dan buat admin default jika belum ada"""
        try:
            # Buat admin default jika belum ada
            await self._ensure_admin_exists()
            
            # Cleanup expired sessions
            await self._cleanup_expired_sessions()
            
            logger.info("UserDatabase initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing UserDatabase: {e}")
            return False
    
    async def _ensure_admin_exists(self):
        """Pastikan akun admin ada"""
        try:
            existing_admin = await db_manager.fetch_one(
                f"SELECT id FROM {self.table_name} WHERE username = %s",
                (Settings.ADMIN_USERNAME,)
            )
            
            if not existing_admin:
                # Buat admin baru
                query = f"""
                    INSERT INTO {self.table_name} 
                    (username, password, is_admin, status, created_at, 
                     total_installs, success_installs, failed_installs)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                await db_manager.execute_query(query, (
                    Settings.ADMIN_USERNAME,
                    Settings.ADMIN_PASSWORD,
                    True,
                    Settings.STATUS_ACTIVE,
                    datetime.now(),
                    0, 0, 0
                ))
                
                logger.info(f"Admin user {Settings.ADMIN_USERNAME} created")
            
        except Exception as e:
            logger.error(f"Error creating admin: {e}")
    
    async def add_user(self, username: str, password: str, telegram_id: int = None) -> Tuple[bool, str]:
        """Tambah user baru"""
        try:
            # Validasi input
            if len(username) < Settings.MIN_USERNAME_LENGTH:
                return False, f"Username minimum {Settings.MIN_USERNAME_LENGTH} characters"
            
            if len(password) < Settings.MIN_PASSWORD_LENGTH:
                return False, f"Password minimum {Settings.MIN_PASSWORD_LENGTH} characters"
            
            if not username.isalnum():
                return False, "Username must be alphanumeric"
            
            # Cek apakah username sudah ada
            existing = await db_manager.fetch_one(
                f"SELECT id FROM {self.table_name} WHERE username = %s",
                (username.lower(),)
            )
            
            if existing:
                return False, "Username already exists"
            
            # Cek apakah telegram_id sudah digunakan (jika ada)
            if telegram_id:
                existing_telegram = await db_manager.fetch_one(
                    f"SELECT id FROM {self.table_name} WHERE telegram_id = %s",
                    (telegram_id,)
                )
                if existing_telegram:
                    return False, "Telegram ID already registered"
            
            # Insert user baru
            query = f"""
                INSERT INTO {self.table_name} 
                (username, password, telegram_id, is_admin, status, created_at, 
                 total_installs, success_installs, failed_installs)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            await db_manager.execute_query(query, (
                username.lower(),
                password,
                telegram_id,  # NULL untuk API users
                False,
                Settings.STATUS_ACTIVE,
                datetime.now(),
                0, 0, 0
            ))
            
            logger.info(f"User {username} added (telegram_id: {telegram_id or 'NULL'})")
            return True, "User created successfully"
            
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False, f"System error: {str(e)}"
    
    async def verify_login(self, username: str, password: str, telegram_id: int = None) -> Tuple[bool, str]:
        """Verifikasi login user dan buat session
        
        Args:
            username: Username user
            password: Password user
            telegram_id: Telegram ID untuk bot login, None/0 untuk API
        """
        try:
            # Cari user berdasarkan username
            user = await db_manager.fetch_one(
                f"SELECT id, password, status, is_admin, telegram_id FROM {self.table_name} WHERE username = %s",
                (username.lower(),)
            )
            
            if not user:
                return False, "Invalid username or password"
            
            # Cek password
            if user['password'] != password:
                return False, "Invalid username or password"
            
            # Cek status user
            if user['status'] == Settings.STATUS_BANNED:
                return False, "Account is banned"
            
            if user['status'] == Settings.STATUS_INACTIVE:
                return False, "Account is inactive"
            
            # Update login info
            if telegram_id and telegram_id != 0:
                # Login dari Telegram Bot - update atau link telegram_id
                update_query = f"""
                    UPDATE {self.table_name} 
                    SET telegram_id = %s, last_login = %s 
                    WHERE id = %s
                """
                await db_manager.execute_query(update_query, (
                    telegram_id,
                    datetime.now(),
                    user['id']
                ))
                
                # Buat session untuk Telegram
                await self._create_user_session(user['id'], telegram_id)
                logger.info(f"User {username} logged in from Telegram {telegram_id}")
                
            else:
                # Login dari API - jangan ubah telegram_id
                update_query = f"""
                    UPDATE {self.table_name} 
                    SET last_login = %s 
                    WHERE id = %s
                """
                await db_manager.execute_query(update_query, (
                    datetime.now(),
                    user['id']
                ))
                logger.info(f"User {username} logged in from API")
            
            return True, "Login successful"
            
        except Exception as e:
            logger.error(f"Error verifying login: {e}")
            return False, "System error occurred"
    
    async def check_session(self, telegram_id: int) -> bool:
        """Cek apakah user session masih valid (untuk Telegram Bot only)"""
        try:
            # Cari session aktif
            session = await db_manager.fetch_one(f"""
                SELECT s.user_id, s.expires_at, u.status
                FROM {self.sessions_table} s
                JOIN {self.table_name} u ON s.user_id = u.id
                WHERE s.telegram_id = %s AND s.is_active = %s AND s.expires_at > %s
                ORDER BY s.login_time DESC
                LIMIT 1
            """, (telegram_id, True, datetime.now()))
            
            if session:
                # Update last activity
                await db_manager.execute_query(f"""
                    UPDATE {self.sessions_table} 
                    SET last_activity = %s 
                    WHERE telegram_id = %s AND is_active = %s
                """, (datetime.now(), telegram_id, True))
                
                return session['status'] == Settings.STATUS_ACTIVE
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking session: {e}")
            return False
    
    async def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Dapatkan user berdasarkan user_id (primary key)"""
        try:
            user = await db_manager.fetch_one(f"""
                SELECT id, username, password, telegram_id, is_admin, status, 
                       created_at, last_login, total_installs, success_installs, failed_installs
                FROM {self.table_name} 
                WHERE id = %s
            """, (user_id,))
            
            if user:
                user_dict = dict(user)
                # Format datetime fields
                if user_dict['created_at']:
                    user_dict['created_at'] = user_dict['created_at'].isoformat()
                if user_dict['last_login']:
                    user_dict['last_login'] = user_dict['last_login'].isoformat()
                
                return user_dict
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user by id: {e}")
            return None
    
    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Tuple[str, Dict]]:
        """Dapatkan user berdasarkan telegram ID"""
        try:
            user = await db_manager.fetch_one(f"""
                SELECT id, username, password, telegram_id, is_admin, status, 
                       created_at, last_login, total_installs, success_installs, failed_installs
                FROM {self.table_name} 
                WHERE telegram_id = %s
            """, (telegram_id,))
            
            if user:
                user_dict = dict(user)
                # Format datetime fields
                if user_dict['created_at']:
                    user_dict['created_at'] = user_dict['created_at'].isoformat()
                if user_dict['last_login']:
                    user_dict['last_login'] = user_dict['last_login'].isoformat()
                
                return user['username'], user_dict
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user by telegram ID: {e}")
            return None
    
    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Dapatkan user berdasarkan username"""
        try:
            user = await db_manager.fetch_one(f"""
                SELECT id, username, password, telegram_id, is_admin, status, 
                       created_at, last_login, total_installs, success_installs, failed_installs
                FROM {self.table_name} 
                WHERE username = %s
            """, (username.lower(),))
            
            if user:
                user_dict = dict(user)
                # Format datetime fields
                if user_dict['created_at']:
                    user_dict['created_at'] = user_dict['created_at'].isoformat()
                if user_dict['last_login']:
                    user_dict['last_login'] = user_dict['last_login'].isoformat()
                
                return user_dict
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user by username: {e}")
            return None
    
    async def is_admin(self, telegram_id: int) -> bool:
        """Cek apakah user adalah admin"""
        try:
            admin_check = await db_manager.fetch_one(f"""
                SELECT is_admin 
                FROM {self.table_name} 
                WHERE telegram_id = %s AND status = %s
            """, (telegram_id, Settings.STATUS_ACTIVE))
            
            return admin_check['is_admin'] if admin_check else False
            
        except Exception as e:
            logger.error(f"Error checking admin: {e}")
            return False
    
    async def logout(self, telegram_id: int) -> bool:
        """Logout user dengan menghapus session"""
        try:
            # Nonaktifkan semua session untuk telegram_id ini
            await db_manager.execute_query(f"""
                UPDATE {self.sessions_table} 
                SET is_active = %s 
                WHERE telegram_id = %s
            """, (False, telegram_id))
            
            logger.info(f"User with telegram_id {telegram_id} logged out")
            return True
            
        except Exception as e:
            logger.error(f"Error logout: {e}")
            return False
    
    async def update_install_stats(self, user_id: int, success: bool) -> bool:
        """Update statistik instalasi user berdasarkan user_id"""
        try:
            if success:
                query = f"""
                    UPDATE {self.table_name} 
                    SET total_installs = total_installs + 1, 
                        success_installs = success_installs + 1
                    WHERE id = %s
                """
            else:
                query = f"""
                    UPDATE {self.table_name} 
                    SET total_installs = total_installs + 1, 
                        failed_installs = failed_installs + 1
                    WHERE id = %s
                """
            
            result = await db_manager.execute_query(query, (user_id,))
            
            if result > 0:
                logger.info(f"Updated install stats for user_id {user_id}: success={success}")
            
            return result > 0
            
        except Exception as e:
            logger.error(f"Error updating install stats: {e}")
            return False
    
    async def delete_user(self, username: str) -> Tuple[bool, str]:
        """Hapus user (admin only)"""
        try:
            if username.lower() == Settings.ADMIN_USERNAME.lower():
                return False, "Cannot delete admin account"
            
            # Cek apakah user ada
            user = await db_manager.fetch_one(
                f"SELECT id FROM {self.table_name} WHERE username = %s",
                (username.lower(),)
            )
            
            if not user:
                return False, "User not found"
            
            # Hapus user (CASCADE akan hapus related records)
            await db_manager.execute_query(
                f"DELETE FROM {self.table_name} WHERE id = %s",
                (user['id'],)
            )
            
            logger.info(f"User {username} deleted")
            return True, "User deleted successfully"
            
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            return False, f"System error: {str(e)}"
    
    async def ban_user(self, username: str) -> Tuple[bool, str]:
        """Ban user"""
        try:
            if username.lower() == Settings.ADMIN_USERNAME.lower():
                return False, "Cannot ban admin account"
            
            result = await db_manager.execute_query(f"""
                UPDATE {self.table_name} 
                SET status = %s 
                WHERE username = %s
            """, (Settings.STATUS_BANNED, username.lower()))
            
            if result > 0:
                # Nonaktifkan semua session user ini
                await db_manager.execute_query(f"""
                    UPDATE {self.sessions_table} 
                    SET is_active = %s 
                    WHERE user_id = (SELECT id FROM {self.table_name} WHERE username = %s)
                """, (False, username.lower()))
                
                return True, f"User {username} banned successfully"
            else:
                return False, "User not found"
                
        except Exception as e:
            logger.error(f"Error banning user: {e}")
            return False, f"System error: {str(e)}"
    
    async def unban_user(self, username: str) -> Tuple[bool, str]:
        """Unban user"""
        try:
            result = await db_manager.execute_query(f"""
                UPDATE {self.table_name} 
                SET status = %s 
                WHERE username = %s AND status = %s
            """, (Settings.STATUS_ACTIVE, username.lower(), Settings.STATUS_BANNED))
            
            if result > 0:
                return True, f"User {username} unbanned successfully"
            else:
                return False, "User not found or not banned"
                
        except Exception as e:
            logger.error(f"Error unbanning user: {e}")
            return False, f"System error: {str(e)}"
    
    async def get_all_telegram_ids(self) -> List[int]:
        """Dapatkan semua telegram ID aktif untuk broadcast"""
        try:
            users = await db_manager.fetch_all(f"""
                SELECT telegram_id 
                FROM {self.table_name} 
                WHERE telegram_id IS NOT NULL AND status = %s
            """, (Settings.STATUS_ACTIVE,))
            
            return [user['telegram_id'] for user in users if user['telegram_id']]
            
        except Exception as e:
            logger.error(f"Error getting all telegram IDs: {e}")
            return []
    
    async def get_user_list(self) -> List[Dict]:
        """Dapatkan daftar semua user"""
        try:
            users = await db_manager.fetch_all(f"""
                SELECT username, is_admin, status, total_installs, success_installs, 
                       failed_installs, created_at, last_login, telegram_id
                FROM {self.table_name} 
                ORDER BY created_at DESC
            """)
            
            formatted_users = []
            for user in users:
                formatted_user = dict(user)
                
                # Format datetime
                if formatted_user['created_at']:
                    formatted_user['created_at'] = formatted_user['created_at'].isoformat()
                else:
                    formatted_user['created_at'] = 'Unknown'
                
                if formatted_user['last_login']:
                    formatted_user['last_login'] = formatted_user['last_login'].isoformat()
                else:
                    formatted_user['last_login'] = 'Never'
                
                formatted_users.append(formatted_user)
            
            return formatted_users
            
        except Exception as e:
            logger.error(f"Error getting user list: {e}")
            return []
    
    async def get_user_stats(self) -> Dict[str, int]:
        """Dapatkan statistik user"""
        try:
            stats = await db_manager.fetch_one(f"""
                SELECT 
                    COUNT(*) as total_users,
                    SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) as active_users,
                    SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) as banned_users,
                    SUM(CASE WHEN is_admin = 1 THEN 1 ELSE 0 END) as admin_users,
                    SUM(CASE WHEN telegram_id IS NOT NULL THEN 1 ELSE 0 END) as users_with_telegram,
                    SUM(CASE WHEN telegram_id IS NULL THEN 1 ELSE 0 END) as api_only_users,
                    SUM(total_installs) as total_installations,
                    SUM(success_installs) as successful_installations,
                    SUM(failed_installs) as failed_installations
                FROM {self.table_name}
            """, (Settings.STATUS_ACTIVE, Settings.STATUS_BANNED))
            
            return dict(stats) if stats else {}
            
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {}
    
    async def _create_user_session(self, user_id: int, telegram_id: int) -> bool:
        """Buat session baru untuk user (Telegram Bot only)"""
        try:
            if not telegram_id or telegram_id == 0:
                logger.debug("Skipping session creation for API user")
                return True
            
            # Nonaktifkan session lama
            await db_manager.execute_query(f"""
                UPDATE {self.sessions_table} 
                SET is_active = %s 
                WHERE user_id = %s
            """, (False, user_id))
            
            # Buat session baru
            expires_at = datetime.now() + timedelta(hours=Settings.SESSION_DURATION_HOURS)
            
            await db_manager.execute_query(f"""
                INSERT INTO {self.sessions_table} 
                (user_id, telegram_id, login_time, last_activity, expires_at, is_active)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                telegram_id,
                datetime.now(),
                datetime.now(),
                expires_at,
                True
            ))
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return False
    
    async def _cleanup_expired_sessions(self):
        """Bersihkan session yang sudah expired"""
        try:
            # Update session expired menjadi inactive
            result = await db_manager.execute_query(f"""
                UPDATE {self.sessions_table} 
                SET is_active = %s 
                WHERE expires_at < %s AND is_active = %s
            """, (False, datetime.now(), True))
            
            if result > 0:
                logger.info(f"Cleaned up {result} expired sessions")
            
            # Hapus session lama yang sudah tidak aktif
            cleanup_date = datetime.now() - timedelta(hours=Settings.CLEANUP_EXPIRED_SESSIONS_HOURS)
            await db_manager.execute_query(f"""
                DELETE FROM {self.sessions_table} 
                WHERE is_active = %s AND last_activity < %s
            """, (False, cleanup_date))
            
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
    
    async def get_active_sessions_count(self, user_id: int = None) -> int:
        """Dapatkan jumlah session aktif"""
        try:
            if user_id:
                result = await db_manager.fetch_one(f"""
                    SELECT COUNT(*) as count 
                    FROM {self.sessions_table} 
                    WHERE user_id = %s AND is_active = %s AND expires_at > %s
                """, (user_id, True, datetime.now()))
            else:
                result = await db_manager.fetch_one(f"""
                    SELECT COUNT(*) as count 
                    FROM {self.sessions_table} 
                    WHERE is_active = %s AND expires_at > %s
                """, (True, datetime.now()))
            
            return result['count'] if result else 0
            
        except Exception as e:
            logger.error(f"Error getting active sessions count: {e}")
            return 0
    
    async def save(self) -> bool:
        """Save method untuk backward compatibility"""
        # Cleanup sessions sebagai pengganti
        await self._cleanup_expired_sessions()
        return True