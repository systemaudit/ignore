"""
MySQL Connection Manager untuk Windows Installer Bot
Mengelola connection pool, transactions, dan database operations
"""

import os
import logging
import asyncio
from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager
import aiomysql
from aiomysql import Pool, Connection
import json
from datetime import datetime

from config.settings import Settings

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception untuk database errors"""
    pass


class ConnectionManager:
    """Manager untuk MySQL connections dengan pool support"""
    
    def __init__(self):
        self.pool: Optional[Pool] = None
        self.config = Settings.DB_CONFIG
        
        self.pool_config = {
            'minsize': 1,
            'maxsize': self.config['pool_size'],
            'pool_recycle': self.config['pool_recycle'],
        }
        
        self.retry_config = {
            'max_attempts': Settings.DB_RETRY_ATTEMPTS,
            'delay': Settings.DB_RETRY_DELAY
        }
    
    async def initialize(self) -> bool:
        """Inisialisasi connection pool"""
        try:
            logger.info("Initializing MySQL connection pool...")
            
            self.pool = await aiomysql.create_pool(
                host=self.config['host'],
                port=self.config['port'],
                user=self.config['user'],
                password=self.config['password'],
                db=self.config['database'],
                charset=self.config['charset'],
                autocommit=False,
                minsize=self.pool_config['minsize'],
                maxsize=self.pool_config['maxsize'],
                pool_recycle=self.pool_config['pool_recycle']
            )
            
            # Test connection
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1")
                    result = await cursor.fetchone()
                    if result[0] != 1:
                        raise DatabaseError("Database connection test failed")
            
            logger.info(f"Connection pool created: {self.config['host']}:{self.config['port']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            return False
    
    async def close(self):
        """Tutup connection pool"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("Connection pool closed")
    
    @asynccontextmanager
    async def get_connection(self):
        """Context manager untuk mendapatkan connection dari pool"""
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")
        
        conn = None
        try:
            conn = await self.pool.acquire()
            yield conn
        except Exception as e:
            if conn:
                await conn.rollback()
            raise DatabaseError(f"Database error: {e}")
        finally:
            if conn:
                self.pool.release(conn)
    
    @asynccontextmanager
    async def transaction(self):
        """Context manager untuk transaksi database"""
        async with self.get_connection() as conn:
            try:
                await conn.begin()
                yield conn
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                raise DatabaseError(f"Transaction error: {e}")
    
    async def execute_query(self, query: str, params: Tuple = None) -> int:
        """Eksekusi query yang mengubah data (INSERT, UPDATE, DELETE)"""
        attempt = 0
        while attempt < self.retry_config['max_attempts']:
            try:
                async with self.get_connection() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(query, params)
                        await conn.commit()
                        return cursor.rowcount
            except Exception as e:
                attempt += 1
                if attempt >= self.retry_config['max_attempts']:
                    logger.error(f"Query execution failed after {attempt} attempts: {e}")
                    raise DatabaseError(f"Query execution failed: {e}")
                
                logger.warning(f"Query attempt {attempt} failed: {e}, retrying in {self.retry_config['delay']}s")
                await asyncio.sleep(self.retry_config['delay'])
    
    async def fetch_one(self, query: str, params: Tuple = None) -> Optional[Dict]:
        """Eksekusi query dan ambil satu row"""
        attempt = 0
        while attempt < self.retry_config['max_attempts']:
            try:
                async with self.get_connection() as conn:
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(query, params)
                        return await cursor.fetchone()
            except Exception as e:
                attempt += 1
                if attempt >= self.retry_config['max_attempts']:
                    logger.error(f"Fetch one failed after {attempt} attempts: {e}")
                    raise DatabaseError(f"Fetch one failed: {e}")
                
                logger.warning(f"Fetch attempt {attempt} failed: {e}, retrying in {self.retry_config['delay']}s")
                await asyncio.sleep(self.retry_config['delay'])
    
    async def fetch_all(self, query: str, params: Tuple = None) -> List[Dict]:
        """Eksekusi query dan ambil semua rows"""
        attempt = 0
        while attempt < self.retry_config['max_attempts']:
            try:
                async with self.get_connection() as conn:
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(query, params)
                        return await cursor.fetchall()
            except Exception as e:
                attempt += 1
                if attempt >= self.retry_config['max_attempts']:
                    logger.error(f"Fetch all failed after {attempt} attempts: {e}")
                    raise DatabaseError(f"Fetch all failed: {e}")
                
                logger.warning(f"Fetch attempt {attempt} failed: {e}, retrying in {self.retry_config['delay']}s")
                await asyncio.sleep(self.retry_config['delay'])
    
    async def execute_transaction(self, operations: List[Tuple[str, Tuple]]) -> bool:
        """Eksekusi multiple operations dalam satu transaksi"""
        try:
            async with self.transaction() as conn:
                async with conn.cursor() as cursor:
                    for query, params in operations:
                        await cursor.execute(query, params)
            return True
        except Exception as e:
            logger.error(f"Transaction failed: {e}")
            return False
    
    async def check_table_exists(self, table_name: str) -> bool:
        """Cek apakah table ada"""
        try:
            query = """
                SELECT COUNT(*) as count 
                FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = %s
            """
            result = await self.fetch_one(query, (self.config['database'], table_name))
            return result['count'] > 0 if result else False
        except Exception as e:
            logger.error(f"Error checking table {table_name}: {e}")
            return False
    
    async def get_database_info(self) -> Dict[str, Any]:
        """Dapatkan informasi database"""
        try:
            # Check MySQL version
            version_result = await self.fetch_one("SELECT VERSION() as version")
            mysql_version = version_result['version'] if version_result else 'Unknown'
            
            # Check tables
            tables = ['users', 'installations', 'installation_logs', 'user_sessions']
            tables_exist = {}
            for table in tables:
                tables_exist[table] = await self.check_table_exists(table)
            
            # Check database size
            size_query = """
                SELECT 
                    table_schema as 'Database',
                    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) as 'Size_MB'
                FROM information_schema.tables 
                WHERE table_schema = %s
                GROUP BY table_schema
            """
            size_result = await self.fetch_one(size_query, (self.config['database'],))
            db_size = size_result['Size_MB'] if size_result else 0
            
            # Check record counts
            record_counts = {}
            for table in tables:
                if tables_exist.get(table, False):
                    try:
                        count_result = await self.fetch_one(f"SELECT COUNT(*) as count FROM {table}")
                        record_counts[table] = count_result['count'] if count_result else 0
                    except:
                        record_counts[table] = 0
                else:
                    record_counts[table] = 0
            
            return {
                'mysql_version': mysql_version,
                'database_name': self.config['database'],
                'database_size_mb': db_size,
                'tables_exist': tables_exist,
                'record_counts': record_counts,
                'connection_pool': await self.get_connection_status()
            }
            
        except Exception as e:
            logger.error(f"Error getting database info: {e}")
            return {
                'error': str(e),
                'tables_exist': {},
                'record_counts': {}
            }
    
    async def get_connection_status(self) -> Dict[str, Any]:
        """Dapatkan status koneksi pool"""
        if not self.pool:
            return {'status': 'not_initialized'}
        
        return {
            'status': 'active',
            'size': self.pool.size,
            'used': self.pool.size - self.pool.freesize,
            'free': self.pool.freesize,
            'maxsize': self.pool.maxsize,
            'minsize': self.pool.minsize
        }
    
    def serialize_json_field(self, data: Any) -> str:
        """Serialize data untuk JSON field"""
        if data is None:
            return None
        return json.dumps(data, ensure_ascii=False)
    
    def deserialize_json_field(self, data: str) -> Any:
        """Deserialize data dari JSON field"""
        if data is None:
            return None
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data


# Global instance
db_manager = ConnectionManager()


# Helper functions untuk backward compatibility
async def init_database() -> bool:
    """Inisialisasi database global"""
    return await db_manager.initialize()


async def close_database():
    """Tutup database global"""
    await db_manager.close()


async def execute_query(query: str, params: Tuple = None) -> int:
    """Execute query helper"""
    return await db_manager.execute_query(query, params)


async def fetch_one(query: str, params: Tuple = None) -> Optional[Dict]:
    """Fetch one helper"""
    return await db_manager.fetch_one(query, params)


async def fetch_all(query: str, params: Tuple = None) -> List[Dict]:
    """Fetch all helper"""
    return await db_manager.fetch_all(query, params)


# Context managers untuk external use
@asynccontextmanager
async def get_connection():
    """Get connection context manager"""
    async with db_manager.get_connection() as conn:
        yield conn


@asynccontextmanager
async def transaction():
    """Transaction context manager"""
    async with db_manager.transaction() as conn:
        yield conn