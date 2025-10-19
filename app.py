"""
Windows Installer Bot API
RESTful API for Windows VPS Installation Service
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
import jwt
import uvicorn

from config.settings import Settings
from database.connection import db_manager, init_database, close_database
from database.users import UserDatabase
from database.installations import InstallationDatabase
from handlers.install import InstallHandler
from utils.helpers import Validators, NotificationService

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, Settings.LOG_LEVEL, logging.INFO),
    handlers=[
        logging.FileHandler(Settings.LOG_DIR / 'api.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Request Models
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    activation_code: str = Field(..., min_length=1, max_length=50)
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        return v.lower()


class UserLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        return v.lower()


class InstallRequest(BaseModel):
    ip: str = Field(..., description="VPS IP address")
    vps_password: str = Field(..., description="VPS root password")
    os_code: str = Field(..., description="Windows OS code")
    rdp_password: str = Field(..., min_length=8, description="RDP password for Windows")
    
    @field_validator('ip')
    @classmethod
    def validate_ip(cls, v):
        if not Validators.validate_ip(v):
            raise ValueError('Invalid IP address format')
        return v
    
    @field_validator('os_code')
    @classmethod
    def validate_os_code(cls, v):
        if not Validators.validate_os_code(v):
            available_codes = ', '.join(Settings.WINDOWS_OS.keys())
            raise ValueError(f'Invalid OS code. Available: {available_codes}')
        return v
    
    @field_validator('rdp_password')
    @classmethod
    def validate_rdp_password(cls, v):
        if not Validators.validate_rdp_password(v):
            raise ValueError('RDP password must be 8+ chars with uppercase, lowercase, and number')
        return v

class APIResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    message: str = ""
    error: Optional[str] = None


# Database instances
user_db = UserDatabase()
install_db = InstallationDatabase()
install_handler = None
notification_service = NotificationService()

# Security
security = HTTPBearer()


def create_token(user_id: int, username: str, is_admin: bool = False) -> str:
    """Create JWT token"""
    payload = {
        'user_id': user_id,
        'username': username,
        'is_admin': is_admin,
        'exp': datetime.utcnow() + timedelta(hours=Settings.JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, Settings.JWT_SECRET, algorithm='HS256')


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """Verify JWT token"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, Settings.JWT_SECRET, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


def get_documentation_html() -> str:
    """API documentation page with responsive design"""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Windows Installer API</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: #fff;
                color: #000;
                line-height: 1.6;
            }
            
            code, pre {
                font-family: 'JetBrains Mono', monospace;
            }
            
            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }
            
            header {
                border-bottom: 2px solid #000;
                padding: 40px 0 30px;
                margin-bottom: 40px;
            }
            
            h1 {
                font-size: clamp(1.8rem, 4vw, 2.5rem);
                font-weight: 600;
                margin-bottom: 10px;
            }
            
            .subtitle {
                color: #666;
                font-size: clamp(0.9rem, 2vw, 1rem);
            }
            
            .nav-menu {
                position: sticky;
                top: 0;
                background: #fff;
                border-bottom: 1px solid #ddd;
                z-index: 100;
                margin: 0 -20px;
                padding: 0 20px;
            }
            
            .nav-menu ul {
                list-style: none;
                display: flex;
                flex-wrap: wrap;
                gap: 10px 20px;
                padding: 15px 0;
            }
            
            .nav-menu a {
                color: #000;
                text-decoration: none;
                font-weight: 500;
                font-size: 0.9rem;
                padding: 5px 10px;
                border: 1px solid transparent;
                transition: all 0.2s;
            }
            
            .nav-menu a:hover {
                background: #f0f0f0;
                border-color: #ddd;
            }
            
            .info-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 40px 0;
            }
            
            .info-card {
                background: #fafafa;
                border: 1px solid #ddd;
                padding: 20px;
            }
            
            .info-card h3 {
                font-size: 0.8rem;
                text-transform: uppercase;
                color: #666;
                margin-bottom: 10px;
                letter-spacing: 0.05em;
            }
            
            .info-card .value {
                font-size: 1.2rem;
                font-weight: 600;
                font-family: 'JetBrains Mono', monospace;
            }
            
            .section {
                margin-bottom: 60px;
                scroll-margin-top: 80px;
            }
            
            h2 {
                font-size: clamp(1.3rem, 3vw, 1.8rem);
                font-weight: 600;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 1px solid #ddd;
            }
            
            h3 {
                font-size: 1.2rem;
                margin: 30px 0 15px;
                font-weight: 600;
            }
            
            .step-card {
                background: #f8f8f8;
                border-left: 4px solid #000;
                padding: 20px;
                margin-bottom: 20px;
            }
            
            .step-number {
                display: inline-block;
                background: #000;
                color: #fff;
                width: 30px;
                height: 30px;
                text-align: center;
                line-height: 30px;
                font-weight: 600;
                margin-bottom: 10px;
                font-size: 0.9rem;
            }
            
            .endpoint {
                background: #fafafa;
                border: 1px solid #e0e0e0;
                padding: 15px;
                margin-bottom: 10px;
                display: flex;
                align-items: center;
                gap: 15px;
                flex-wrap: wrap;
                transition: background 0.2s;
            }
            
            .endpoint:hover {
                background: #f0f0f0;
            }
            
            .method {
                font-weight: 600;
                font-size: 0.75rem;
                padding: 4px 10px;
                text-align: center;
                min-width: 50px;
            }
            
            .method.get { background: #000; color: #fff; }
            .method.post { background: #333; color: #fff; }
            
            .endpoint-path {
                flex: 1;
                font-family: 'JetBrains Mono', monospace;
                font-size: 0.9rem;
                min-width: 200px;
            }
            
            .endpoint-desc {
                color: #666;
                font-size: 0.85rem;
            }
            
            .auth-badge {
                background: #fff;
                border: 1px solid #999;
                color: #666;
                padding: 2px 8px;
                font-size: 0.7rem;
                font-weight: 600;
            }
            
            .code-block {
                background: #f8f8f8;
                border: 1px solid #ddd;
                padding: 20px;
                margin: 20px 0;
                overflow-x: auto;
                position: relative;
            }
            
            .code-block pre {
                font-size: 0.85rem;
                line-height: 1.5;
                white-space: pre-wrap;
                word-break: break-word;
            }
            
            .code-lang {
                position: absolute;
                top: 5px;
                right: 10px;
                background: #000;
                color: #fff;
                padding: 2px 8px;
                font-size: 0.7rem;
                font-weight: 600;
            }
            
            .copy-btn {
                position: absolute;
                top: 5px;
                right: 60px;
                background: #fff;
                border: 1px solid #000;
                padding: 2px 8px;
                font-size: 0.7rem;
                cursor: pointer;
                transition: all 0.2s;
            }
            
            .copy-btn:hover {
                background: #000;
                color: #fff;
            }
            
            .tabs {
                display: flex;
                gap: 10px;
                margin-bottom: 20px;
                border-bottom: 1px solid #ddd;
            }
            
            .tab {
                padding: 10px 20px;
                background: none;
                border: none;
                font-weight: 500;
                cursor: pointer;
                border-bottom: 2px solid transparent;
                transition: all 0.2s;
            }
            
            .tab.active {
                border-bottom-color: #000;
            }
            
            .tab-content {
                display: none;
            }
            
            .tab-content.active {
                display: block;
            }
            
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
                font-size: 0.9rem;
            }
            
            th, td {
                text-align: left;
                padding: 12px;
                border-bottom: 1px solid #ddd;
            }
            
            th {
                background: #fafafa;
                font-weight: 600;
            }
            
            td code {
                background: #f0f0f0;
                padding: 2px 6px;
                font-size: 0.85em;
            }
            
            .alert {
                background: #fffbf0;
                border: 1px solid #f0e0a0;
                padding: 15px;
                margin: 20px 0;
            }
            
            .alert.info {
                background: #f0f8ff;
                border-color: #a0d0f0;
            }
            
            .alert.success {
                background: #f0fff0;
                border-color: #a0f0a0;
            }
            
            .footer {
                margin-top: 80px;
                padding: 30px 0;
                border-top: 1px solid #ddd;
                text-align: center;
                color: #666;
                font-size: 0.9rem;
            }
            
            @media (max-width: 768px) {
                .container {
                    padding: 15px;
                }
                
                header {
                    padding: 20px 0;
                }
                
                .nav-menu {
                    margin: 0 -15px;
                    padding: 0 15px;
                }
                
                .info-grid {
                    grid-template-columns: 1fr;
                }
                
                .endpoint {
                    flex-direction: column;
                    align-items: flex-start;
                }
                
                .code-block {
                    padding: 15px;
                }
                
                .code-block pre {
                    font-size: 0.75rem;
                }
                
                table {
                    font-size: 0.8rem;
                }
                
                th, td {
                    padding: 8px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>Windows Installer API</h1>
                <p class="subtitle">Automated Windows Installation Service for VPS</p>
            </header>
            
            <nav class="nav-menu">
                <ul>
                    <li><a href="#quickstart">Quick Start</a></li>
                    <li><a href="#authentication">Authentication</a></li>
                    <li><a href="#installation">Installation</a></li>
                    <li><a href="#endpoints">All Endpoints</a></li>
                    <li><a href="#examples">Examples</a></li>
                    <li><a href="#errors">Errors</a></li>
                </ul>
            </nav>
            
            <div class="info-grid">
                <div class="info-card">
                    <h3>Base URL</h3>
                    <div class="value">api.mysticpage.id</div>
                </div>
                <div class="info-card">
                    <h3>Authentication</h3>
                    <div class="value">JWT Token</div>
                </div>
                <div class="info-card">
                    <h3>RDP Port</h3>
                    <div class="value">22</div>
                </div>
            </div>
            
            <section id="quickstart" class="section">
                <h2>Quick Start Guide</h2>
                
                <div class="step-card">
                    <span class="step-number">1</span>
                    <h3>Register Account</h3>
                    <p>Create your account with activation code</p>
                    <div class="code-block">
                        <span class="code-lang">CURL</span>
                        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                        <pre>curl -X POST https://api.mysticpage.id/auth/register \\
  -H "Content-Type: application/json" \\
  -d '{
    "username": "yourusername",
    "password": "yourpassword",
    "activation_code": "winux"
  }'</pre>
                    </div>
                </div>
                
                <div class="step-card">
                    <span class="step-number">2</span>
                    <h3>Login to Get Token</h3>
                    <p>Get your JWT token for authentication</p>
                    <div class="code-block">
                        <span class="code-lang">CURL</span>
                        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                        <pre>curl -X POST https://api.mysticpage.id/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{
    "username": "yourusername",
    "password": "yourpassword"
  }'</pre>
                    </div>
                    <div class="alert info">
                        <strong>Response:</strong> Save the <code>token</code> value from response. You'll need it for all other requests.
                    </div>
                </div>
                
                <div class="step-card">
                    <span class="step-number">3</span>
                    <h3>Start Installation</h3>
                    <p>Install Windows on your VPS</p>
                    <div class="code-block">
                        <span class="code-lang">CURL</span>
                        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                        <pre>curl -X POST https://api.mysticpage.id/install \\
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \\
  -H "Content-Type: application/json" \\
  -d '{
    "ip": "192.168.1.100",
    "vps_password": "your_vps_root_password",
    "os_code": "w11pro",
    "rdp_password": "Windows123!"
  }'</pre>
                    </div>
                </div>
                
                <div class="step-card">
                    <span class="step-number">4</span>
                    <h3>Monitor Progress</h3>
                    <p>Check installation status using install_id</p>
                    <div class="code-block">
                        <span class="code-lang">CURL</span>
                        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                        <pre>curl -X GET https://api.mysticpage.id/install/install_1_abc123 \\
  -H "Authorization: Bearer YOUR_TOKEN_HERE"</pre>
                    </div>
                </div>
            </section>
            
            <section id="authentication" class="section">
                <h2>Authentication</h2>
                
                <h3>Register New Account</h3>
                <div class="endpoint">
                    <span class="method post">POST</span>
                    <span class="endpoint-path">/auth/register</span>
                    <span class="endpoint-desc">Create new account</span>
                </div>
                
                <div class="tabs">
                    <button class="tab active" onclick="showTab(this, 'reg-curl')">CURL</button>
                    <button class="tab" onclick="showTab(this, 'reg-python')">Python</button>
                    <button class="tab" onclick="showTab(this, 'reg-js')">JavaScript</button>
                </div>
                
                <div id="reg-curl" class="tab-content active">
                    <div class="code-block">
                        <span class="code-lang">CURL</span>
                        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                        <pre>curl -X POST https://api.mysticpage.id/auth/register \\
  -H "Content-Type: application/json" \\
  -d '{
    "username": "john",
    "password": "SecurePass123",
    "activation_code": "winux"
  }'</pre>
                    </div>
                </div>
                
                <div id="reg-python" class="tab-content">
                    <div class="code-block">
                        <span class="code-lang">Python</span>
                        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                        <pre>import requests

response = requests.post(
    "https://api.mysticpage.id/auth/register",
    json={
        "username": "john",
        "password": "SecurePass123",
        "activation_code": "winux"
    }
)
print(response.json())</pre>
                    </div>
                </div>
                
                <div id="reg-js" class="tab-content">
                    <div class="code-block">
                        <span class="code-lang">JavaScript</span>
                        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                        <pre>fetch('https://api.mysticpage.id/auth/register', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    username: 'john',
    password: 'SecurePass123',
    activation_code: 'winux'
  })
})
.then(res => res.json())
.then(data => console.log(data));</pre>
                    </div>
                </div>
                
                <h3>Login</h3>
                <div class="endpoint">
                    <span class="method post">POST</span>
                    <span class="endpoint-path">/auth/login</span>
                    <span class="endpoint-desc">Get JWT token</span>
                </div>
                
                <div class="tabs">
                    <button class="tab active" onclick="showTab(this, 'login-curl')">CURL</button>
                    <button class="tab" onclick="showTab(this, 'login-python')">Python</button>
                    <button class="tab" onclick="showTab(this, 'login-js')">JavaScript</button>
                </div>
                
                <div id="login-curl" class="tab-content active">
                    <div class="code-block">
                        <span class="code-lang">CURL</span>
                        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                        <pre>curl -X POST https://api.mysticpage.id/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{
    "username": "john",
    "password": "SecurePass123"
  }'

# Response:
{
  "success": true,
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_in": 86400
  }
}</pre>
                    </div>
                </div>
                
                <div id="login-python" class="tab-content">
                    <div class="code-block">
                        <span class="code-lang">Python</span>
                        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                        <pre>import requests

response = requests.post(
    "https://api.mysticpage.id/auth/login",
    json={
        "username": "john",
        "password": "SecurePass123"
    }
)
data = response.json()
token = data['data']['token']
print(f"Token: {token}")</pre>
                    </div>
                </div>
                
                <div id="login-js" class="tab-content">
                    <div class="code-block">
                        <span class="code-lang">JavaScript</span>
                        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                        <pre>fetch('https://api.mysticpage.id/auth/login', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    username: 'john',
    password: 'SecurePass123'
  })
})
.then(res => res.json())
.then(data => {
  const token = data.data.token;
  localStorage.setItem('token', token);
  console.log('Token saved:', token);
});</pre>
                    </div>
                </div>
            </section>
            
            <section id="installation" class="section">
                <h2>Installation Process</h2>
                
                <h3>Available Windows OS</h3>
                <table>
                    <thead>
                        <tr>
                            <th>OS Code</th>
                            <th>Operating System</th>
                            <th>Type</th>
                            <th>Min RAM</th>
                            <th>Min Disk</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr><td><code>ws2012r2</code></td><td>Windows Server 2012 R2</td><td>Server</td><td>2GB</td><td>30GB</td></tr>
                        <tr><td><code>ws2016</code></td><td>Windows Server 2016</td><td>Server</td><td>2GB</td><td>30GB</td></tr>
                        <tr><td><code>ws2019</code></td><td>Windows Server 2019</td><td>Server</td><td>2GB</td><td>30GB</td></tr>
                        <tr><td><code>ws2022</code></td><td>Windows Server 2022</td><td>Server</td><td>2GB</td><td>30GB</td></tr>
                        <tr><td><code>ws2025</code></td><td>Windows Server 2025</td><td>Server</td><td>2GB</td><td>30GB</td></tr>
                        <tr><td><code>w10pro</code></td><td>Windows 10 Pro</td><td>Desktop</td><td>2GB</td><td>30GB</td></tr>
                        <tr><td><code>w10atlas</code></td><td>Windows 10 Atlas</td><td>Desktop</td><td>2GB</td><td>30GB</td></tr>
                        <tr><td><code>w11pro</code></td><td>Windows 11 Pro</td><td>Desktop</td><td>2GB</td><td>30GB</td></tr>
                        <tr><td><code>w11atlas</code></td><td>Windows 11 Atlas</td><td>Desktop</td><td>2GB</td><td>30GB</td></tr>
                    </tbody>
                </table>
                
                <h3>Start Installation</h3>
                <div class="endpoint">
                    <span class="method post">POST</span>
                    <span class="endpoint-path">/install</span>
                    <span class="endpoint-desc">Start Windows installation</span>
                    <span class="auth-badge">JWT</span>
                </div>
                
                <div class="code-block">
                    <span class="code-lang">CURL</span>
                    <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                    <pre>curl -X POST https://api.mysticpage.id/install \\
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \\
  -H "Content-Type: application/json" \\
  -d '{
    "ip": "192.168.1.100",
    "vps_password": "vps_root_password",
    "os_code": "w11pro",
    "rdp_password": "Windows123!"
  }'

# Response:
{
  "success": true,
  "data": {
    "install_id": "install_1_abc123",
    "status": "starting",
    "monitor_url": "/install/install_1_abc123"
  },
  "message": "Installation started"
}</pre>
                </div>
                
                <div class="alert info">
                    <strong>RDP Password Requirements:</strong>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>Minimum 8 characters</li>
                        <li>At least one uppercase letter</li>
                        <li>At least one lowercase letter</li>
                        <li>At least one number</li>
                    </ul>
                </div>
                
                <h3>Monitor Installation</h3>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/install/{install_id}</span>
                    <span class="endpoint-desc">Get installation status</span>
                    <span class="auth-badge">JWT</span>
                </div>
                
                <div class="code-block">
                    <span class="code-lang">CURL</span>
                    <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                    <pre>curl -X GET https://api.mysticpage.id/install/install_1_abc123 \\
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# Response:
{
  "success": true,
  "data": {
    "install_id": "install_1_abc123",
    "status": "installing",
    "progress": 50,
    "current_step": "Installing Windows",
    "ip": "192.168.1.100",
    "os_name": "Windows 11 Pro"
  }
}</pre>
                </div>
                
                <h3>Installation Progress</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Status</th>
                            <th>Progress</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr><td><code>starting</code></td><td>5%</td><td>Initializing installation</td></tr>
                        <tr><td><code>connecting</code></td><td>10%</td><td>Connecting to VPS</td></tr>
                        <tr><td><code>checking</code></td><td>20%</td><td>Checking system requirements</td></tr>
                        <tr><td><code>preparing</code></td><td>30%</td><td>Preparing installation files</td></tr>
                        <tr><td><code>installing</code></td><td>50%</td><td>Installing Windows</td></tr>
                        <tr><td><code>monitoring</code></td><td>80%</td><td>Monitoring installation</td></tr>
                        <tr><td><code>completed</code></td><td>100%</td><td>Installation complete</td></tr>
                        <tr><td><code>failed</code></td><td>0%</td><td>Installation failed</td></tr>
                    </tbody>
                </table>
                
                <div class="alert success">
                    <strong>When Completed:</strong> The response will include <code>rdp_info</code> with connection details:
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>IP Address</li>
                        <li>Port: 22</li>
                        <li>Username: Administrator</li>
                        <li>Password: Your RDP password</li>
                    </ul>
                </div>
            </section>
            
            <section id="endpoints" class="section">
                <h2>All Endpoints</h2>
                
                <h3>Public Endpoints</h3>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/</span>
                    <span class="endpoint-desc">Documentation page</span>
                </div>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/health</span>
                    <span class="endpoint-desc">Health check</span>
                </div>
                <div class="endpoint">
                    <span class="method post">POST</span>
                    <span class="endpoint-path">/auth/register</span>
                    <span class="endpoint-desc">Register account</span>
                </div>
                <div class="endpoint">
                    <span class="method post">POST</span>
                    <span class="endpoint-path">/auth/login</span>
                    <span class="endpoint-desc">Login to get token</span>
                </div>
                
                <h3>Protected Endpoints (JWT Required)</h3>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/user/profile</span>
                    <span class="endpoint-desc">Get user profile</span>
                    <span class="auth-badge">JWT</span>
                </div>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/os/list</span>
                    <span class="endpoint-desc">List available OS</span>
                    <span class="auth-badge">JWT</span>
                </div>
                <div class="endpoint">
                    <span class="method post">POST</span>
                    <span class="endpoint-path">/install</span>
                    <span class="endpoint-desc">Start installation</span>
                    <span class="auth-badge">JWT</span>
                </div>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/install/{install_id}</span>
                    <span class="endpoint-desc">Get installation status</span>
                    <span class="auth-badge">JWT</span>
                </div>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/install/list</span>
                    <span class="endpoint-desc">List user installations</span>
                    <span class="auth-badge">JWT</span>
                </div>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <span class="endpoint-path">/install/{install_id}/logs</span>
                    <span class="endpoint-desc">Get installation logs</span>
                    <span class="auth-badge">JWT</span>
                </div>
            </section>
            
            <section id="examples" class="section">
                <h2>Complete Examples</h2>
                
                <h3>Python Script</h3>
                <div class="code-block">
                    <span class="code-lang">Python</span>
                    <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                    <pre>import requests
import time

BASE_URL = "https://api.mysticpage.id"

# 1. Register (skip if already registered)
register_data = {
    "username": "myuser",
    "password": "MyPass123",
    "activation_code": "winux"
}
requests.post(f"{BASE_URL}/auth/register", json=register_data)

# 2. Login
login_data = {
    "username": "myuser",
    "password": "MyPass123"
}
response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
token = response.json()['data']['token']

# 3. Setup headers
headers = {"Authorization": f"Bearer {token}"}

# 4. Start installation
install_data = {
    "ip": "192.168.1.100",
    "vps_password": "vps_root_pass",
    "os_code": "w11pro",
    "rdp_password": "Windows123!"
}
response = requests.post(f"{BASE_URL}/install", json=install_data, headers=headers)
install_id = response.json()['data']['install_id']

# 5. Monitor progress
while True:
    response = requests.get(f"{BASE_URL}/install/{install_id}", headers=headers)
    data = response.json()['data']
    
    print(f"Status: {data['status']} - Progress: {data['progress']}%")
    
    if data['status'] in ['completed', 'failed', 'timeout']:
        if data['status'] == 'completed':
            rdp_info = data['rdp_info']
            print(f"RDP Ready at {rdp_info['ip']}:{rdp_info['port']}")
            print(f"Username: {rdp_info['username']}")
            print(f"Password: {rdp_info['password']}")
        break
    
    time.sleep(30)  # Check every 30 seconds</pre>
                </div>
                
                <h3>JavaScript (Node.js)</h3>
                <div class="code-block">
                    <span class="code-lang">JavaScript</span>
                    <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                    <pre>const axios = require('axios');

const BASE_URL = 'https://api.mysticpage.id';

async function installWindows() {
  try {
    // 1. Login
    const loginRes = await axios.post(`${BASE_URL}/auth/login`, {
      username: 'myuser',
      password: 'MyPass123'
    });
    const token = loginRes.data.data.token;
    
    // 2. Setup headers
    const config = {
      headers: { Authorization: `Bearer ${token}` }
    };
    
    // 3. Start installation
    const installRes = await axios.post(`${BASE_URL}/install`, {
      ip: '192.168.1.100',
      vps_password: 'vps_root_pass',
      os_code: 'w11pro',
      rdp_password: 'Windows123!'
    }, config);
    
    const installId = installRes.data.data.install_id;
    console.log('Installation started:', installId);
    
    // 4. Monitor progress
    const checkStatus = async () => {
      const res = await axios.get(`${BASE_URL}/install/${installId}`, config);
      const data = res.data.data;
      
      console.log(`Status: ${data.status} - Progress: ${data.progress}%`);
      
      if (['completed', 'failed', 'timeout'].includes(data.status)) {
        if (data.status === 'completed') {
          console.log('RDP Info:', data.rdp_info);
        }
        return;
      }
      
      setTimeout(checkStatus, 30000); // Check every 30 seconds
    };
    
    await checkStatus();
    
  } catch (error) {
    console.error('Error:', error.response?.data || error.message);
  }
}

installWindows();</pre>
                </div>
            </section>
            
            <section id="errors" class="section">
                <h2>Error Handling</h2>
                
                <table>
                    <thead>
                        <tr>
                            <th>HTTP Code</th>
                            <th>Error Type</th>
                            <th>Solution</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>400</td>
                            <td>Bad Request</td>
                            <td>Check your request parameters</td>
                        </tr>
                        <tr>
                            <td>401</td>
                            <td>Unauthorized</td>
                            <td>Token expired or invalid. Login again</td>
                        </tr>
                        <tr>
                            <td>403</td>
                            <td>Forbidden</td>
                            <td>You don't have access to this resource</td>
                        </tr>
                        <tr>
                            <td>404</td>
                            <td>Not Found</td>
                            <td>Resource doesn't exist</td>
                        </tr>
                        <tr>
                            <td>500</td>
                            <td>Server Error</td>
                            <td>Try again later or contact support</td>
                        </tr>
                    </tbody>
                </table>
                
                <h3>Common Issues</h3>
                <div class="alert">
                    <strong>Invalid activation code:</strong> Contact admin for the correct code
                </div>
                <div class="alert">
                    <strong>Username already exists:</strong> Try a different username
                </div>
                <div class="alert">
                    <strong>Invalid RDP password:</strong> Must be 8+ chars with uppercase, lowercase, and number
                </div>
                <div class="alert">
                    <strong>Installation failed:</strong> Check VPS requirements (Ubuntu/Debian, 2GB RAM, 30GB disk)
                </div>
            </section>
            
            <div class="footer">
                <p>Windows Installer API</p>
                <p>Support: ${Settings.ADMIN_CONTACT}</p>
            </div>
        </div>
        
        <script>
            function showTab(btn, contentId) {
                // Get parent tabs container
                const tabsContainer = btn.parentElement;
                const section = tabsContainer.parentElement;
                
                // Remove active from all tabs in this section
                tabsContainer.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                
                // Hide all tab contents in this section
                section.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                
                // Add active to clicked tab and show content
                btn.classList.add('active');
                document.getElementById(contentId).classList.add('active');
            }
            
            function copyCode(btn) {
                const codeBlock = btn.parentElement.querySelector('pre');
                const text = codeBlock.textContent;
                
                navigator.clipboard.writeText(text).then(() => {
                    const originalText = btn.textContent;
                    btn.textContent = 'Copied!';
                    setTimeout(() => {
                        btn.textContent = originalText;
                    }, 2000);
                });
            }
        </script>
    </body>
    </html>
    """


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager"""
    global install_handler
    
    logger.info("Starting API server...")
    
    # Initialize database
    success = await init_database()
    if not success:
        logger.error("Failed to initialize database")
        raise RuntimeError("Database initialization failed")
    
    # Initialize database managers
    await user_db.initialize()
    await install_db.initialize()
    
    # Initialize install handler
    install_handler = InstallHandler(user_db, install_db)
    
    # Setup notification service
    notification_service.set_databases(user_db, install_db)
    install_handler.notification_service = notification_service
    
    # Cleanup stuck installations
    await install_db.cleanup_stuck_installations()
    
    logger.info("API server started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down API server...")
    await close_database()
    logger.info("API server stopped")


# FastAPI application
app = FastAPI(
    title="Windows Installer API",
    description="Automated Windows installation service for VPS",
    lifespan=lifespan,
    docs_url="/docs" if Settings.ENVIRONMENT == "development" else "/docs",
    redoc_url="/redoc" if Settings.ENVIRONMENT == "development" else "/redoc",
    openapi_url="/openapi.json"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "message": "Internal server error",
            "error": str(exc) if Settings.ENVIRONMENT == "development" else "An error occurred"
        }
    )


# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def root():
    """API documentation page"""
    return get_documentation_html()


# Health check
@app.get("/health")
async def health_check():
    """Check API and database health"""
    try:
        db_status = await db_manager.get_connection_status()
        return {
            "success": True,
            "data": {
                "status": "healthy",
                "database": db_status.get('status') == 'active',
                "environment": Settings.ENVIRONMENT
            },
            "message": "Service is healthy"
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "message": "Health check failed",
            "error": str(e)
        }


# Authentication endpoints
@app.post("/auth/register", response_model=APIResponse)
async def register(user_data: UserRegister):
    """Register new user account"""
    try:
        # Validate activation code
        if user_data.activation_code != Settings.ACTIVATION_CODE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid activation code. Contact {Settings.ADMIN_CONTACT}"
            )
        
        # Register user with telegram_id=NULL for API users
        success, message = await user_db.add_user(
            user_data.username,
            user_data.password,
            telegram_id=None
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )
        
        return APIResponse(
            success=True,
            data={"username": user_data.username},
            message="Registration successful. Please login to get your token."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


@app.post("/auth/login")
async def login(credentials: UserLogin):
    """Login and receive JWT token"""
    try:
        # Verify login with telegram_id=0 for API login
        success, message = await user_db.verify_login(
            credentials.username,
            credentials.password,
            telegram_id=0
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=message
            )
        
        # Get user data
        user = await user_db.get_user_by_username(credentials.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Create JWT token
        token = create_token(
            user_id=user['id'],
            username=user['username'],
            is_admin=user.get('is_admin', False)
        )
        
        return {
            "success": True,
            "data": {
                "token": token,
                "token_type": "bearer",
                "expires_in": Settings.JWT_EXPIRATION_HOURS * 3600,
                "user": {
                    "username": user['username'],
                    "is_admin": user.get('is_admin', False),
                    "telegram_linked": user.get('telegram_id') is not None
                }
            },
            "message": "Login successful"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


# User endpoints
@app.get("/user/profile", response_model=APIResponse)
async def get_profile(payload: Dict = Depends(verify_token)):
    """Get current user profile"""
    try:
        user = await user_db.get_user_by_id(payload['user_id'])
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Remove sensitive data
        user.pop('password', None)
        user['telegram_linked'] = user.get('telegram_id') is not None
        
        return APIResponse(
            success=True,
            data=user,
            message="Profile retrieved successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get profile error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve profile"
        )


# OS endpoints
@app.get("/os/list", response_model=APIResponse)
async def list_operating_systems(payload: Dict = Depends(verify_token)):
    """List available Windows operating systems"""
    try:
        os_list = []
        for code, info in Settings.WINDOWS_OS.items():
            os_list.append({
                "code": code,
                "name": info['name'],
                "category": info.get('category', 'desktop'),
                "min_ram": info['min_ram'],
                "min_disk": info['min_disk']
            })
        
        return APIResponse(
            success=True,
            data={
                "operating_systems": os_list,
                "requirements": {
                    "min_ram": "2GB",
                    "min_disk": "30GB",
                    "supported_host_os": ["ubuntu", "debian"],
                    "rdp_port": Settings.RDP_PORT
                }
            },
            message="OS list retrieved"
        )
        
    except Exception as e:
        logger.error(f"OS list error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve OS list"
        )


# Installation endpoints
@app.post("/install", response_model=APIResponse)
async def start_installation(
    install_data: InstallRequest,
    background_tasks: BackgroundTasks,
    payload: Dict = Depends(verify_token)
):
    """Start Windows installation on VPS"""
    try:
        user_id = payload['user_id']
        
        # Get OS info
        os_info = Settings.WINDOWS_OS[install_data.os_code]
        
        # Create installation record
        install_id = await install_db.create_installation(user_id, {
            'ip': install_data.ip,
            'os_code': install_data.os_code,
            'os_name': os_info['name'],
            'boot_mode': 'unknown'
        })
        
        if not install_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create installation record"
            )
        
        # Start installation in background
        background_tasks.add_task(
            install_handler.process_installation,
            user_id=user_id,
            install_data={
                'ip': install_data.ip,
                'vps_password': install_data.vps_password,
                'os_code': install_data.os_code,
                'os_name': os_info['name'],
                'rdp_password': install_data.rdp_password,
                'boot_mode': 'unknown'
            },
            source="api"
        )
        
        return APIResponse(
            success=True,
            data={
                "install_id": install_id,
                "status": "starting",
                "ip": install_data.ip,
                "os": os_info['name'],
                "monitor_url": f"/install/{install_id}"
            },
            message="Installation started. Monitor progress using the install_id."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Installation start error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/install/{install_id}", response_model=APIResponse)
async def get_installation_status(
    install_id: str,
    payload: Dict = Depends(verify_token)
):
    """Get specific installation status and details"""
    try:
        installation = await install_db.get(install_id)
        
        if not installation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Installation not found"
            )
        
        # Check ownership
        if installation['user_id'] != payload['user_id'] and not payload.get('is_admin'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Calculate progress percentage
        status_progress = {
            Settings.INSTALL_STATUS_STARTING: 5,
            Settings.INSTALL_STATUS_CONNECTING: 10,
            Settings.INSTALL_STATUS_CHECKING: 20,
            Settings.INSTALL_STATUS_PREPARING: 30,
            Settings.INSTALL_STATUS_INSTALLING: 50,
            Settings.INSTALL_STATUS_MONITORING: 80,
            Settings.INSTALL_STATUS_COMPLETED: 100,
            Settings.INSTALL_STATUS_FAILED: 0,
            Settings.INSTALL_STATUS_TIMEOUT: 0
        }
        
        progress = status_progress.get(installation['status'], 0)
        
        # Prepare response data
        response_data = {
            "install_id": installation['install_id'],
            "status": installation['status'],
            "progress": progress,
            "current_step": installation.get('current_step', ''),
            "ip": installation['ip'],
            "os_name": installation['os_name'],
            "start_time": installation['start_time'],
            "end_time": installation.get('end_time'),
            "error": installation.get('error'),
            "rdp_info": installation.get('rdp_info') if installation['status'] == Settings.INSTALL_STATUS_COMPLETED else None
        }
        
        # Add last 10 logs
        if 'logs' in installation:
            response_data['logs'] = installation['logs'][-10:]
        
        return APIResponse(
            success=True,
            data=response_data,
            message="Installation details retrieved"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get installation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve installation"
        )


@app.get("/install/list", response_model=APIResponse)
async def list_installations(
    status: Optional[str] = None,
    limit: int = 20,
    payload: Dict = Depends(verify_token)
):
    """List user installations"""
    try:
        installations = await install_db.get_user_installations(
            payload['user_id'],
            status
        )
        
        # Limit results
        installations = installations[:limit]
        
        # Calculate progress for each
        status_progress = {
            Settings.INSTALL_STATUS_STARTING: 5,
            Settings.INSTALL_STATUS_CONNECTING: 10,
            Settings.INSTALL_STATUS_CHECKING: 20,
            Settings.INSTALL_STATUS_PREPARING: 30,
            Settings.INSTALL_STATUS_INSTALLING: 50,
            Settings.INSTALL_STATUS_MONITORING: 80,
            Settings.INSTALL_STATUS_COMPLETED: 100,
            Settings.INSTALL_STATUS_FAILED: 0,
            Settings.INSTALL_STATUS_TIMEOUT: 0
        }
        
        for install in installations:
            install['progress'] = status_progress.get(install['status'], 0)
        
        return APIResponse(
            success=True,
            data=installations,
            message=f"Found {len(installations)} installation(s)"
        )
        
    except Exception as e:
        logger.error(f"List installations error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve installations"
        )


@app.get("/install/{install_id}/logs", response_model=APIResponse)
async def get_installation_logs(
    install_id: str,
    limit: int = 50,
    payload: Dict = Depends(verify_token)
):
    """Get installation logs"""
    try:
        installation = await install_db.get(install_id)
        
        if not installation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Installation not found"
            )
        
        # Check ownership
        if installation['user_id'] != payload['user_id'] and not payload.get('is_admin'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        logs = await install_db.get_logs(install_id, limit)
        
        return APIResponse(
            success=True,
            data={
                "install_id": install_id,
                "logs": logs,
                "count": len(logs)
            },
            message=f"Retrieved {len(logs)} log entries"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get logs error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve logs"
        )


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=Settings.API_HOST,
        port=Settings.API_PORT,
        reload=Settings.ENVIRONMENT == "development",
        workers=Settings.API_WORKERS if Settings.ENVIRONMENT == "production" else 1,
        log_level=Settings.LOG_LEVEL.lower()
    )
