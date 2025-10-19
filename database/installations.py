"""
Database tracking untuk instalasi Windows
Support untuk cross-platform notifications dan unified installation flow
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from database.connection import db_manager
from config.settings import Settings

logger = logging.getLogger(__name__)


class InstallationDatabase:
    """Database untuk tracking instalasi"""
    
    def __init__(self):
        self.table_name = 'installations'
        self.logs_table = 'installation_logs'
    
    async def initialize(self):
        """Inisialisasi database"""
        try:
            # Cleanup instalasi yang stuck atau lama
            await self.cleanup_stuck_installations()
            await self.cleanup_old_installations(days=Settings.CLEANUP_OLD_INSTALLS_DAYS)
            
            logger.info("InstallationDatabase initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing InstallationDatabase: {e}")
            return False
    
    async def create_installation(self, user_id: int, install_data: Dict) -> str:
        """Buat record instalasi baru"""
        try:
            install_id = f"install_{user_id}_{uuid.uuid4().hex[:8]}"
            
            insert_query = f"""
                INSERT INTO {self.table_name} 
                (install_id, user_id, status, start_time, ip, os_code, os_name, 
                 boot_mode, current_step, last_update)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            now = datetime.now()
            
            await db_manager.execute_query(insert_query, (
                install_id,
                user_id,
                Settings.INSTALL_STATUS_STARTING,
                now,
                install_data.get('ip', ''),
                install_data.get('os_code', ''),
                install_data.get('os_name', ''),
                install_data.get('boot_mode', 'unknown'),
                'Starting installation',
                now
            ))
            
            # Log instalasi dimulai
            await self.add_log(install_id, 'Installation started')
            
            logger.info(f"Installation {install_id} created for user {user_id} at {install_data.get('ip')}")
            return install_id
            
        except Exception as e:
            logger.error(f"Error creating installation: {e}")
            return ""
    
    async def update_status(self, install_id: str, status: str, extra_data: Dict = None) -> bool:
        """Update status instalasi"""
        try:
            now = datetime.now()
            
            # Base update
            update_fields = ['status = %s', 'last_update = %s']
            params = [status, now]
            
            # Handle status khusus
            if status == Settings.INSTALL_STATUS_COMPLETED:
                update_fields.append('end_time = %s')
                update_fields.append('current_step = %s')
                params.extend([now, 'Installation complete'])
                
                if extra_data and 'rdp_info' in extra_data:
                    update_fields.append('rdp_info = %s')
                    # Ensure port is always 22
                    rdp_info = extra_data['rdp_info']
                    rdp_info['port'] = Settings.RDP_PORT
                    params.append(db_manager.serialize_json_field(rdp_info))
                
                if extra_data and 'boot_mode' in extra_data:
                    update_fields.append('boot_mode = %s')
                    params.append(extra_data['boot_mode'])
                    
            elif status == Settings.INSTALL_STATUS_FAILED:
                update_fields.append('end_time = %s')
                update_fields.append('current_step = %s')
                error_msg = extra_data.get('error', 'Unknown error') if extra_data else 'Unknown error'
                update_fields.append('error = %s')
                params.extend([now, f"Failed: {error_msg[:100]}", error_msg])
                
            elif status == Settings.INSTALL_STATUS_TIMEOUT:
                update_fields.append('end_time = %s')
                update_fields.append('current_step = %s')
                update_fields.append('error = %s')
                params.extend([now, 'Installation timeout', 'Installation exceeded 30 minutes timeout'])
            
            # Add install_id untuk WHERE clause
            params.append(install_id)
            
            query = f"""
                UPDATE {self.table_name} 
                SET {', '.join(update_fields)}
                WHERE install_id = %s
            """
            
            result = await db_manager.execute_query(query, tuple(params))
            
            if result > 0:
                # Log perubahan status
                await self.add_log(install_id, f"Status changed to: {status}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            return False
    
    async def update_step(self, install_id: str, step: str) -> bool:
        """Update langkah instalasi saat ini"""
        try:
            query = f"""
                UPDATE {self.table_name} 
                SET current_step = %s, last_update = %s 
                WHERE install_id = %s
            """
            
            result = await db_manager.execute_query(query, (
                step,
                datetime.now(),
                install_id
            ))
            
            if result > 0:
                # Tambah ke log
                await self.add_log(install_id, step)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error updating step: {e}")
            return False
    
    async def add_log(self, install_id: str, message: str) -> bool:
        """Tambah log entry untuk instalasi"""
        try:
            query = f"""
                INSERT INTO {self.logs_table} (install_id, timestamp, message)
                VALUES (%s, %s, %s)
            """
            
            await db_manager.execute_query(query, (
                install_id,
                datetime.now(),
                message
            ))
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding log: {e}")
            return False
    
    async def get_logs(self, install_id: str, limit: int = 50) -> List[Dict]:
        """Dapatkan logs untuk instalasi"""
        try:
            query = f"""
                SELECT timestamp, message 
                FROM {self.logs_table} 
                WHERE install_id = %s 
                ORDER BY timestamp DESC 
                LIMIT %s
            """
            
            logs = await db_manager.fetch_all(query, (install_id, limit))
            
            # Format logs
            formatted_logs = []
            for log in logs:
                formatted_logs.append({
                    'time': log['timestamp'].isoformat(),
                    'message': log['message']
                })
            
            return list(reversed(formatted_logs))  # Reverse untuk urutan chronological
            
        except Exception as e:
            logger.error(f"Error getting logs: {e}")
            return []
    
    async def get_user_installations(self, user_id: int, status: str = None) -> List[Dict]:
        """Dapatkan semua instalasi untuk user"""
        try:
            base_query = f"""
                SELECT install_id, user_id, status, start_time, end_time, ip, 
                       os_code, os_name, boot_mode, current_step, error, rdp_info, last_update
                FROM {self.table_name} 
                WHERE user_id = %s
            """
            
            params = [user_id]
            
            if status:
                base_query += " AND status = %s"
                params.append(status)
            
            base_query += " ORDER BY start_time DESC"
            
            installations = await db_manager.fetch_all(base_query, tuple(params))
            
            # Format installations
            formatted_installations = []
            for install in installations:
                formatted_install = dict(install)
                
                # Format datetime fields
                if formatted_install['start_time']:
                    formatted_install['start_time'] = formatted_install['start_time'].isoformat()
                
                if formatted_install['end_time']:
                    formatted_install['end_time'] = formatted_install['end_time'].isoformat()
                
                if formatted_install['last_update']:
                    formatted_install['last_update'] = formatted_install['last_update'].isoformat()
                
                # Deserialize JSON fields
                if formatted_install['rdp_info']:
                    formatted_install['rdp_info'] = db_manager.deserialize_json_field(formatted_install['rdp_info'])
                    # Ensure port is always 22
                    if formatted_install['rdp_info']:
                        formatted_install['rdp_info']['port'] = Settings.RDP_PORT
                
                formatted_installations.append(formatted_install)
            
            return formatted_installations
            
        except Exception as e:
            logger.error(f"Error getting user installations: {e}")
            return []
    
    async def get_active_installations(self, user_id: int = None) -> List[Dict]:
        """Dapatkan semua instalasi yang masih aktif"""
        try:
            active_statuses = [
                Settings.INSTALL_STATUS_STARTING,
                Settings.INSTALL_STATUS_CONNECTING,
                Settings.INSTALL_STATUS_CHECKING,
                Settings.INSTALL_STATUS_PREPARING,
                Settings.INSTALL_STATUS_INSTALLING,
                Settings.INSTALL_STATUS_MONITORING
            ]
            
            # Build query dengan IN clause
            status_placeholders = ', '.join(['%s'] * len(active_statuses))
            
            base_query = f"""
                SELECT install_id, user_id, status, start_time, ip, os_code, os_name, 
                       boot_mode, current_step, last_update
                FROM {self.table_name} 
                WHERE status IN ({status_placeholders})
            """
            
            params = active_statuses
            
            if user_id is not None:
                base_query += " AND user_id = %s"
                params.append(user_id)
            
            base_query += " ORDER BY start_time DESC"
            
            installations = await db_manager.fetch_all(base_query, tuple(params))
            
            # Format installations
            formatted_installations = []
            for install in installations:
                formatted_install = dict(install)
                
                # Format datetime fields
                if formatted_install['start_time']:
                    formatted_install['start_time'] = formatted_install['start_time'].isoformat()
                
                if formatted_install['last_update']:
                    formatted_install['last_update'] = formatted_install['last_update'].isoformat()
                
                formatted_installations.append(formatted_install)
            
            return formatted_installations
            
        except Exception as e:
            logger.error(f"Error getting active installations: {e}")
            return []
    
    async def get(self, install_id: str) -> Optional[Dict]:
        """Dapatkan instalasi berdasarkan ID"""
        try:
            installation = await db_manager.fetch_one(f"""
                SELECT install_id, user_id, status, start_time, end_time, ip, 
                       os_code, os_name, boot_mode, current_step, error, rdp_info, last_update
                FROM {self.table_name} 
                WHERE install_id = %s
            """, (install_id,))
            
            if not installation:
                return None
            
            formatted_installation = dict(installation)
            
            # Format datetime fields
            if formatted_installation['start_time']:
                formatted_installation['start_time'] = formatted_installation['start_time'].isoformat()
            
            if formatted_installation['end_time']:
                formatted_installation['end_time'] = formatted_installation['end_time'].isoformat()
            
            if formatted_installation['last_update']:
                formatted_installation['last_update'] = formatted_installation['last_update'].isoformat()
            
            # Deserialize JSON fields
            if formatted_installation['rdp_info']:
                formatted_installation['rdp_info'] = db_manager.deserialize_json_field(formatted_installation['rdp_info'])
                # Ensure port is always 22
                if formatted_installation['rdp_info']:
                    formatted_installation['rdp_info']['port'] = Settings.RDP_PORT
            
            # Add logs
            formatted_installation['logs'] = await self.get_logs(install_id, 50)
            
            return formatted_installation
            
        except Exception as e:
            logger.error(f"Error getting installation: {e}")
            return None
    
    async def cleanup_old_installations(self, days: int = None) -> int:
        """Hapus instalasi lama yang sudah selesai"""
        try:
            days = days or Settings.CLEANUP_OLD_INSTALLS_DAYS
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Hapus instalasi lama yang sudah completed/failed/timeout
            query = f"""
                DELETE FROM {self.table_name} 
                WHERE start_time < %s 
                AND status IN (%s, %s, %s)
            """
            
            result = await db_manager.execute_query(query, (
                cutoff_date,
                Settings.INSTALL_STATUS_COMPLETED,
                Settings.INSTALL_STATUS_FAILED,
                Settings.INSTALL_STATUS_TIMEOUT
            ))
            
            if result > 0:
                logger.info(f"Cleaned up {result} old installations (>{days} days)")
            
            return result
            
        except Exception as e:
            logger.error(f"Error cleaning up old installations: {e}")
            return 0
    
    async def cleanup_stuck_installations(self) -> int:
        """Cleanup instalasi yang stuck/timeout"""
        try:
            timeout_seconds = Settings.TIMEOUT_INSTALLATION
            cutoff_time = datetime.now() - timedelta(seconds=timeout_seconds)
            
            active_statuses = [
                Settings.INSTALL_STATUS_STARTING,
                Settings.INSTALL_STATUS_CONNECTING,
                Settings.INSTALL_STATUS_CHECKING,
                Settings.INSTALL_STATUS_PREPARING,
                Settings.INSTALL_STATUS_INSTALLING,
                Settings.INSTALL_STATUS_MONITORING
            ]
            
            # Build query untuk update stuck installations
            status_placeholders = ', '.join(['%s'] * len(active_statuses))
            
            query = f"""
                UPDATE {self.table_name} 
                SET status = %s, 
                    error = %s, 
                    end_time = %s, 
                    current_step = %s,
                    last_update = %s
                WHERE start_time < %s 
                AND status IN ({status_placeholders})
            """
            
            params = [
                Settings.INSTALL_STATUS_TIMEOUT,
                'Installation timeout (30 minutes)',
                datetime.now(),
                'Installation timeout',
                datetime.now(),
                cutoff_time
            ] + active_statuses
            
            result = await db_manager.execute_query(query, tuple(params))
            
            if result > 0:
                logger.info(f"Cleaned up {result} stuck installations")
            
            return result
            
        except Exception as e:
            logger.error(f"Error cleaning up stuck installations: {e}")
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Dapatkan statistik instalasi"""
        try:
            # Basic stats
            basic_stats = await db_manager.fetch_one(f"""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status IN (%s, %s, %s, %s, %s, %s) THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) as timeout
                FROM {self.table_name}
            """, (
                Settings.INSTALL_STATUS_STARTING,
                Settings.INSTALL_STATUS_CONNECTING,
                Settings.INSTALL_STATUS_CHECKING,
                Settings.INSTALL_STATUS_PREPARING,
                Settings.INSTALL_STATUS_INSTALLING,
                Settings.INSTALL_STATUS_MONITORING,
                Settings.INSTALL_STATUS_COMPLETED,
                Settings.INSTALL_STATUS_FAILED,
                Settings.INSTALL_STATUS_TIMEOUT
            ))
            
            # Stats per OS
            os_stats = await db_manager.fetch_all(f"""
                SELECT os_code, COUNT(*) as count 
                FROM {self.table_name} 
                GROUP BY os_code 
                ORDER BY count DESC
            """)
            
            # Recent installations (24 jam terakhir)
            recent_count = await db_manager.fetch_one(f"""
                SELECT COUNT(*) as count 
                FROM {self.table_name} 
                WHERE start_time >= %s
            """, (datetime.now() - timedelta(hours=24),))
            
            # Success rate
            total = basic_stats['total'] if basic_stats else 0
            completed = basic_stats['completed'] if basic_stats else 0
            success_rate = (completed / total * 100) if total > 0 else 0
            
            return {
                'total': total,
                'active': basic_stats['active'] if basic_stats else 0,
                'completed': completed,
                'failed': basic_stats['failed'] if basic_stats else 0,
                'timeout': basic_stats['timeout'] if basic_stats else 0,
                'success_rate': round(success_rate, 2),
                'recent_24h': recent_count['count'] if recent_count else 0,
                'os_stats': {item['os_code']: item['count'] for item in os_stats}
            }
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {
                'total': 0,
                'active': 0,
                'completed': 0,
                'failed': 0,
                'timeout': 0,
                'success_rate': 0.0,
                'recent_24h': 0,
                'os_stats': {}
            }
    
    async def get_installations_by_status(self, status: str, limit: int = 100) -> List[Dict]:
        """Dapatkan instalasi berdasarkan status"""
        try:
            query = f"""
                SELECT install_id, user_id, status, start_time, end_time, ip, 
                       os_code, os_name, boot_mode, current_step, last_update
                FROM {self.table_name} 
                WHERE status = %s 
                ORDER BY start_time DESC 
                LIMIT %s
            """
            
            installations = await db_manager.fetch_all(query, (status, limit))
            
            formatted_installations = []
            for install in installations:
                formatted_install = dict(install)
                
                # Format datetime fields
                if formatted_install['start_time']:
                    formatted_install['start_time'] = formatted_install['start_time'].isoformat()
                
                if formatted_install['end_time']:
                    formatted_install['end_time'] = formatted_install['end_time'].isoformat()
                
                if formatted_install['last_update']:
                    formatted_install['last_update'] = formatted_install['last_update'].isoformat()
                
                formatted_installations.append(formatted_install)
            
            return formatted_installations
            
        except Exception as e:
            logger.error(f"Error getting installations by status: {e}")
            return []
    
    async def get_recent_installations(self, hours: int = 24, limit: int = 100) -> List[Dict]:
        """Dapatkan instalasi terbaru dalam X jam terakhir"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            query = f"""
                SELECT install_id, user_id, status, start_time, end_time, ip, 
                       os_code, os_name, boot_mode, current_step, last_update
                FROM {self.table_name} 
                WHERE start_time >= %s 
                ORDER BY start_time DESC 
                LIMIT %s
            """
            
            installations = await db_manager.fetch_all(query, (cutoff_time, limit))
            
            formatted_installations = []
            for install in installations:
                formatted_install = dict(install)
                
                # Format datetime fields
                if formatted_install['start_time']:
                    formatted_install['start_time'] = formatted_install['start_time'].isoformat()
                
                if formatted_install['end_time']:
                    formatted_install['end_time'] = formatted_install['end_time'].isoformat()
                
                if formatted_install['last_update']:
                    formatted_install['last_update'] = formatted_install['last_update'].isoformat()
                
                formatted_installations.append(formatted_install)
            
            return formatted_installations
            
        except Exception as e:
            logger.error(f"Error getting recent installations: {e}")
            return []
    
    async def delete_installation(self, install_id: str) -> bool:
        """Hapus instalasi dan semua logs terkait"""
        try:
            # CASCADE akan otomatis hapus logs
            result = await db_manager.execute_query(
                f"DELETE FROM {self.table_name} WHERE install_id = %s",
                (install_id,)
            )
            
            return result > 0
            
        except Exception as e:
            logger.error(f"Error deleting installation: {e}")
            return False
    
    async def cleanup_old_logs(self, days: int = None) -> int:
        """Cleanup logs yang sudah lama"""
        try:
            days = days or Settings.CLEANUP_OLD_LOGS_DAYS
            cutoff_date = datetime.now() - timedelta(days=days)
            
            result = await db_manager.execute_query(
                f"DELETE FROM {self.logs_table} WHERE timestamp < %s",
                (cutoff_date,)
            )
            
            if result > 0:
                logger.info(f"Cleaned up {result} old logs (>{days} days)")
            
            return result
            
        except Exception as e:
            logger.error(f"Error cleaning up old logs: {e}")
            return 0
    
    async def save(self) -> bool:
        """Save method untuk backward compatibility"""
        # Cleanup sebagai pengganti
        await self.cleanup_stuck_installations()
        await self.cleanup_old_logs()
        return True