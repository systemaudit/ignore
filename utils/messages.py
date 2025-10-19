"""
Template pesan untuk bot dalam bahasa Inggris
Simpel, tanpa emoji, langsung ke point
"""

from config.settings import Settings


class Messages:
    """Template pesan bot"""
    
    # Pesan Welcome & Auth
    WELCOME = """Windows Installer Bot

Automated Windows installation for VPS.

Commands:
/login username password - Login to your account
/register username password code - Create new account

Need help? Use /help"""
    
    WELCOME_BACK = "Welcome back, {username}!\n\nUse /menu to see available commands."
    
    # Login
    LOGIN_FORMAT = "Format: /login username password"
    LOGIN_SUCCESS = "Login successful. Welcome, {username}!"
    LOGIN_FAILED = "Login failed: {reason}"
    
    # Register
    REGISTER_FORMAT = "Format: /register username password {activation_code}\n\nGet activation code from {contact}"
    REGISTER_SUCCESS = "Registration successful!\n\nUsername: {username}\nPassword: {password}\n\nLogin with: /login {username} {password}"
    REGISTER_FAILED = "Registration failed: {reason}"
    INVALID_ACTIVATION = "Invalid activation code. Contact {contact} for the code."
    
    # Logout
    LOGOUT_SUCCESS = "Logged out successfully."
    LOGOUT_FAILED = "Logout failed. Please try again."
    
    # Session
    ALREADY_LOGGED_IN = "You are already logged in. Use /menu for available commands."
    NOT_LOGGED_IN = "Please login first: /login username password"
    SESSION_EXPIRED = "Session expired. Please login again."
    
    # Menu
    MAIN_MENU = """Main Menu

Commands:
/install - Install Windows to VPS
/oslist - List available Windows versions  
/history - Installation history
/profile - Account information
/help - User guide
/logout - Sign out

Support: {contact}
Channel: {channel}"""
    
    ADMIN_MENU_EXTRA = "\n\nAdmin: /adminpanel"
    
    # Installation
    INSTALL_USAGE = """Format: /install ip password os_code rdp_password

Example:
/install 192.168.1.100 vpspass w10pro MyPass123

Requirements:
- VPS must be Ubuntu/Debian with root access
- RDP password: min 8 chars (uppercase, lowercase, number)
- Use /oslist to see available OS codes"""
    
    # Installation Progress Steps
    INSTALL_STEP_CONNECTING = "Connecting to {ip}..."
    INSTALL_STEP_CONNECTED = "Connected to {ip}"
    INSTALL_STEP_CHECKING = "Checking system specifications..."
    INSTALL_STEP_CHECKED = "System check passed"
    INSTALL_STEP_PREPARING = "Preparing installation files..."
    INSTALL_STEP_PREPARED = "Installation prepared successfully"
    INSTALL_STEP_INSTALLING = "Installing Windows to {ip}..."
    INSTALL_STEP_MONITORING = """Installation running...

Monitoring: {ip}:80
System will notify when complete"""
    
    # Installation Results
    INSTALL_SUCCESS_RESULT = """Installation successful

IP: {ip}
Port: {port}
Username: Administrator
Password: {password}

Windows is ready for RDP connection"""
    
    INSTALL_FAILED_RESULT = """Installation failed

IP: {ip}
Error: {error}

Please check VPS requirements"""
    
    INSTALL_TIMEOUT_RESULT = """Installation timeout

IP: {ip}
Port: {port}
Password: {password}

Installation exceeded 30 minutes
Try connecting manually"""
    
    # Installation Error Details
    INSTALL_ERROR_RAM = "Insufficient RAM ({available}GB available, {required}GB required)"
    INSTALL_ERROR_DISK = "Insufficient disk space ({available}GB available, {required}GB required)"
    INSTALL_ERROR_OS = "Unsupported OS: {os_type} (Ubuntu/Debian required)"
    INSTALL_ERROR_CONNECTION = "Connection failed: {error}"
    INSTALL_ERROR_PREPARATION = "Preparation failed: {error}"
    INSTALL_ERROR_GENERIC = "System error: {error}"
    
    # OS List
    OS_LIST = """Available Windows Versions

Server Editions:
{servers}

Desktop Editions:
{desktops}

Requirements:
- RAM: 2GB minimum
- Disk: 30GB minimum
- Host: Ubuntu/Debian
- RDP Port: 22 (automatic)"""
    
    # Profile
    USER_PROFILE = """Profile Information

Username: {username}
Status: {status}
Total Installations: {total}
Successful: {success}
Failed: {failed}
Success Rate: {success_rate:.1f}%
Joined: {created}
Last Login: {last_login}"""
    
    # History
    NO_INSTALLATION_HISTORY = "No installation history found."
    INSTALLATION_HISTORY_HEADER = "Installation History (last 10):\n"
    
    # Admin
    ADMIN_MENU = """Admin Panel

System Status:
CPU: {cpu:.1f}%
RAM: {ram_percent:.1f}% ({ram_used}GB / {ram_total}GB)
Disk: {disk_percent:.1f}% ({disk_used}GB / {disk_total}GB)

Installation Status:
Active: {active}
Total: {total}
Successful: {completed}
Failed: {failed}

Admin Commands:
/userlist - List all users
/adduser - Add new user
/deleteuser - Delete user
/banuser - Ban user
/unbanuser - Unban user  
/broadcast - Send message to all users
/cleanup - Clean old data
/logs - View system logs
/dbstatus - Database status
/dbstats - Database statistics"""
    
    ADMIN_ONLY = "This command requires admin privileges."
    ADMIN_STATS_ERROR = "Failed to retrieve system statistics."
    
    # User Management
    USER_LIST_HEADER = "User List:\n"
    NO_USERS_FOUND = "No users found."
    ADDUSER_FORMAT = "Format: /adduser username password"
    USER_ADDED = "User {username} added successfully."
    USER_ADD_FAILED = "Failed to add user: {reason}"
    DELETEUSER_FORMAT = "Format: /deleteuser username"
    USER_DELETED = "User {username} deleted successfully."
    USER_DELETE_FAILED = "Failed to delete user: {reason}"
    BANUSER_FORMAT = "Format: /banuser username"
    USER_BANNED = "User {username} banned successfully."
    USER_BAN_FAILED = "Failed to ban user: {reason}"
    UNBANUSER_FORMAT = "Format: /unbanuser username"
    USER_UNBANNED = "User {username} unbanned successfully."
    USER_UNBAN_FAILED = "Failed to unban user: {reason}"
    
    # Broadcast
    BROADCAST_FORMAT = "Format: /broadcast your message"
    BROADCAST_MESSAGE = "Admin Announcement:\n\n{message}"
    BROADCAST_SENT = "Broadcast sent.\nSuccessful: {success}\nFailed: {failed}\nTotal: {total}"
    NO_ACTIVE_USERS = "No active users found for broadcast."
    
    # Cleanup
    CLEANUP_DONE = "Cleanup complete.\nStuck installations: {stuck}\nOld installations: {old}\nTotal cleaned: {total}"
    
    # Database Status
    DB_STATUS_HEADER = "Database Status\n\nConnection: {status}\nActive Connections: {active}/{max}\nDatabase Size: {size}MB"
    DB_STATS_HEADER = "Database Statistics\n\nUsers: {users}\nInstallations: {installations}\nSuccess Rate: {rate}%"
    
    # Logs
    LOG_FILE_NOT_FOUND = "Log file not found."
    LOG_CONTENT = "System Logs (last 50 lines):\n\n{content}"
    LOG_READ_ERROR = "Failed to read log file."
    
    # Generic Errors
    ERROR_GENERIC = "System error. Please try again or contact admin."
    ERROR_INVALID_IP = "Invalid IP address format."
    ERROR_INVALID_PASSWORD = "Password requirements:\n- Minimum 8 characters\n- Must contain uppercase letter\n- Must contain lowercase letter\n- Must contain number"
    ERROR_INVALID_OS = "Invalid OS code. Use /oslist to see available options."
    
    # Other
    UNKNOWN_COMMAND = "Unknown command. Use /help for available commands."
    USE_MENU = "Use /menu to see available features."
    USER_NOT_FOUND = "User data not found."
    
    # Help
    HELP_TEXT = """User Guide

How to Install Windows:
1. Login: /login username password
2. Install: /install ip vps_password os_code rdp_password
3. Wait 15-20 minutes for completion
4. Connect via RDP on port 22

Available OS Codes:
ws2012r2 - Windows Server 2012 R2
ws2016 - Windows Server 2016
ws2019 - Windows Server 2019
ws2022 - Windows Server 2022
ws2025 - Windows Server 2025
w10pro - Windows 10 Pro
w10atlas - Windows 10 Atlas
w11pro - Windows 11 Pro
w11atlas - Windows 11 Atlas

VPS Requirements:
- OS: Ubuntu or Debian
- RAM: Minimum 2GB
- Disk: Minimum 30GB
- Root access with password
- Port 22 (SSH) open

RDP Information:
- Port 22 is used for RDP (all providers allow this)
- After Windows installation, SSH is no longer available
- Use Remote Desktop Connection to access

Troubleshooting:
- Can't connect to RDP? Wait 5-10 minutes
- Installation failed? Check VPS requirements
- SSH error? Verify root password

Support: {contact}"""
    
    # Notification Messages untuk cross-platform
    NOTIFICATION_INSTALL_STARTED = "Installation started for {ip}\nOS: {os_name}\nID: {install_id}"
    NOTIFICATION_INSTALL_PROGRESS = "Installation progress for {ip}: {step}"
    NOTIFICATION_INSTALL_COMPLETED = "Installation complete!\n\nRDP: {ip}:22\nUsername: Administrator\nPassword: {password}"
    NOTIFICATION_INSTALL_FAILED = "Installation failed for {ip}\nError: {error}"
    NOTIFICATION_INSTALL_TIMEOUT = "Installation timeout for {ip}\nPlease check manually"