import os
import tempfile
import threading
import time
from datetime import datetime
from functools import lru_cache, wraps
from collections import OrderedDict
import logging
import json
import re
import mimetypes
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv

from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import pyodbc
import sqlite3

# Load environment variables from .env file
load_dotenv()

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create separate loggers for different components
upload_logger = logging.getLogger('upload')
db_logger = logging.getLogger('database')
security_logger = logging.getLogger('security')

app = Flask(__name__)

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.environ.get("REDIS_URL", "memory://")  # Use REDIS_URL from env, fallback to memory
)
limiter.init_app(app)

# Configure secret key
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY')
if not SECRET_KEY:
    if app.debug:
        logger.warning("FLASK_SECRET_KEY environment variable not set. Using a default insecure key for development. DO NOT RUN IN PRODUCTION WITHOUT SETTING THIS.")
        SECRET_KEY = "dev-debug-key-must-not-be-used-in-prod-and-is-very-long-to-meet-entropy-reqs" # Ensure it's long enough
    else:
        logger.error("FLASK_SECRET_KEY is not set. Application will not run in production mode without it.")
        raise ValueError("FLASK_SECRET_KEY is not set. Application cannot start in non-debug mode.")
app.secret_key = SECRET_KEY

# Initialize CSRF Protection
csrf = CSRFProtect(app)

# Admin Token Configuration
DBVIEWER_ADMIN_TOKEN = os.environ.get('DBVIEWER_ADMIN_TOKEN')
if not DBVIEWER_ADMIN_TOKEN and not app.debug:
    logger.warning("DBVIEWER_ADMIN_TOKEN is not set. Destructive operations will be disabled.")
elif not DBVIEWER_ADMIN_TOKEN and app.debug:
    logger.warning("DBVIEWER_ADMIN_TOKEN is not set. Using a default insecure token for development: 'admin-debug-token'. DO NOT USE IN PRODUCTION.")
    DBVIEWER_ADMIN_TOKEN = "admin-debug-token"

app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max file size
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')

# Allowed extensions
ALLOWED_EXTENSIONS = {'mdb', 'accdb', 'sqlite', 'db'}

# Cache for database connections and queries
connection_cache = OrderedDict()
MAX_CACHE_SIZE = 10

# Thread lock for cache operations
cache_lock = threading.Lock()

# Security configuration
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_MIME_TYPES = {
    'application/vnd.ms-access',
    'application/x-msaccess',
    'application/vnd.sqlite3',
    'application/x-sqlite3',
    'application/octet-stream'  # For .db files
}

def handle_database_error(func):
    """Decorator for database operation error handling"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except pyodbc.Error as e:
            db_logger.error(f"Database error in {func.__name__}: {e}")
            raise Exception(f"Database operation failed: {str(e)}")
        except sqlite3.Error as e:
            db_logger.error(f"SQLite error in {func.__name__}: {e}")
            raise Exception(f"SQLite operation failed: {str(e)}")
        except Exception as e:
            db_logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise
    return wrapper

def validate_file_content(filepath: str) -> bool:
    """Validate file content beyond extension checking"""
    try:
        # Check file size
        if os.path.getsize(filepath) > MAX_UPLOAD_SIZE:
            return False
            
        # Read first few bytes to identify file type
        with open(filepath, 'rb') as f:
            header = f.read(32)
            
        # SQLite files start with 'SQLite format 3\000'
        if header.startswith(b'SQLite format 3'):
            return True
            
        # Access database files have specific signatures
        # .mdb files typically start with specific bytes
        if header.startswith(b'\x00\x01\x00\x00Standard Jet DB') or \
           header.startswith(b'\x00\x01\x00\x00Standard ACE DB'):
            return True
            
        # Additional checks for other Access formats
        if b'Microsoft' in header[:32] or b'Access' in header[:32]:
            return True
            
        return False
    except Exception as e:
        security_logger.warning(f"File validation failed for {filepath}: {e}")
        return False

def sanitize_filename(filename: str) -> str:
    """Enhanced filename sanitization"""
    # Remove path traversal attempts
    filename = os.path.basename(filename)
    # Remove non-alphanumeric characters except dots, underscores, and hyphens
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    # Ensure it doesn't start with a dot
    if filename.startswith('.'):
        filename = 'file_' + filename
    return filename

def log_security_event(event_type: str, details: Dict[str, Any], remote_addr: str = None):
    """Log security-related events"""
    remote_addr = remote_addr or request.remote_addr if request else 'unknown'
    security_logger.warning(f"Security event: {event_type} from {remote_addr} - {details}")

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_database_info(filepath):
    """Get basic database information"""
    try:
        conn = get_db_connection(filepath)
        tables = get_tables(conn)
        file_size = os.path.getsize(filepath)
        modified_time = datetime.fromtimestamp(os.path.getmtime(filepath))
        
        return {
            'filepath': filepath,
            'filename': os.path.basename(filepath),
            'original_name': os.path.basename(filepath).split('_', 1)[-1] if '_' in os.path.basename(filepath) else os.path.basename(filepath),
            'tables': tables,
            'table_count': len(tables),
            'file_size': file_size,
            'modified_time': modified_time.isoformat(),
            'upload_time': datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting database info for {filepath}: {e}")
        return None

def get_all_databases():
    """Get information about all uploaded databases"""
    databases = []
    upload_folder = app.config['UPLOAD_FOLDER']
    
    if not os.path.exists(upload_folder):
        return databases
    
    for filename in os.listdir(upload_folder):
        if allowed_file(filename):
            filepath = os.path.join(upload_folder, filename)
            if os.path.isfile(filepath):
                db_info = get_database_info(filepath)
                if db_info:
                    databases.append(db_info)
    
    # Sort by upload time (newest first)
    databases.sort(key=lambda x: x['modified_time'], reverse=True)
    return databases

def get_connection_string(filepath):
    """Generate connection string for Access database"""
    if filepath.endswith('.accdb'):
        return f'DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={filepath};ExtendedAnsiSQL=1;'
    else:
        return f'DRIVER={{Microsoft Access Driver (*.mdb)}};DBQ={filepath};ExtendedAnsiSQL=1;'

@handle_database_error
def get_db_connection(filepath: str):
    """Get database connection with caching and improved error handling"""
    if not os.path.exists(filepath):
        db_logger.error(f"Database file not found: {filepath}")
        raise FileNotFoundError(f"Database file not found: {filepath}")
    
    with cache_lock:
        if filepath in connection_cache:
            # Test connection before returning cached one
            try:
                conn = connection_cache[filepath]
                # Test the connection with a simple query
                cursor = conn.cursor()
                if isinstance(conn, pyodbc.Connection):
                    cursor.execute("SELECT 1")
                else:  # SQLite
                    cursor.execute("SELECT 1")
                cursor.fetchone()
                # Move to end (LRU) if connection is good
                connection_cache.move_to_end(filepath)
                db_logger.debug(f"Reusing cached connection for {filepath}")
                return conn
            except Exception as e:
                db_logger.warning(f"Cached connection invalid for {filepath}: {e}")
                # Remove invalid connection from cache
                connection_cache.pop(filepath, None)
        
        # Remove oldest if cache is full
        if len(connection_cache) >= MAX_CACHE_SIZE:
            oldest = next(iter(connection_cache))
            old_conn = connection_cache.pop(oldest)
            try:
                old_conn.close()
                db_logger.debug(f"Closed oldest cached connection: {oldest}")
            except Exception as e:
                db_logger.warning(f"Error closing old connection: {e}")
        
        # Create new connection
        file_ext = filepath.rsplit('.', 1)[-1].lower()
        conn = None

        if file_ext in ['mdb', 'accdb']:
            try:
                conn_str = get_connection_string(filepath)
                conn = pyodbc.connect(conn_str, timeout=30)
                # Set encoding with better error handling
                try:
                    conn.setdecoding(pyodbc.SQL_CHAR, encoding='utf-8')
                    conn.setdecoding(pyodbc.SQL_WCHAR, encoding='utf-8')
                    conn.setencoding(encoding='utf-8')
                except Exception as encoding_error:
                    db_logger.warning(f"Could not set encoding for Access DB {filepath}: {encoding_error}")
                
                # Test the connection
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                
                db_logger.info(f"Successfully connected to Access DB: {filepath}")
            except Exception as e:
                db_logger.error(f"Failed to connect to Access DB {filepath}: {e}")
                raise ConnectionError(f"Failed to connect to Access database: {str(e)}")
                
        elif file_ext in ['sqlite', 'db']:
            try:
                # Add timeout and other SQLite optimizations
                conn = sqlite3.connect(
                    filepath, 
                    check_same_thread=False,
                    timeout=30.0
                )
                # Enable WAL mode for better concurrent access
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA cache_size=10000")
                
                # Test the connection
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                
                db_logger.info(f"Successfully connected to SQLite DB: {filepath}")
            except Exception as e:
                db_logger.error(f"Failed to connect to SQLite DB {filepath}: {e}")
                raise ConnectionError(f"Failed to connect to SQLite database: {str(e)}")
        else:
            error_msg = f"Unsupported database type: {file_ext} for file {filepath}"
            db_logger.error(error_msg)
            raise ValueError(error_msg)

        if conn:
            connection_cache[filepath] = conn
            return conn
        else:
            error_msg = f"Failed to establish database connection for {filepath}"
            db_logger.error(error_msg)
            raise ConnectionError(error_msg)

def get_tables(conn):
    """Get list of tables from database"""
    tables = []
    try:
        if isinstance(conn, pyodbc.Connection):
            cursor = conn.cursor()
            try:
                for table_info in cursor.tables(tableType='TABLE'):
                    try:
                        table_name = str(table_info.table_name) if table_info.table_name else None
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        # Skip tables with encoding issues
                        continue
                    
                    if table_name and not table_name.startswith('MSys'):
                        tables.append(table_name)
            except Exception as e:
                logger.warning(f"Error getting tables with standard method: {e}")
                # Fallback method using system tables
                try:
                    cursor.execute("SELECT Name FROM MSysObjects WHERE Type=1 AND Flags=0")
                    for row in cursor.fetchall():
                        try:
                            table_name = str(row[0]) if row[0] else None
                        except (UnicodeDecodeError, UnicodeEncodeError):
                            continue
                        
                        if table_name and not table_name.startswith('MSys'):
                            tables.append(table_name)
                except Exception as fallback_e:
                    logger.warning(f"Fallback method failed: {fallback_e}")
                    # Last resort: try to find tables by querying schema
                    try:
                        cursor.execute("SELECT DISTINCT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'")
                        for row in cursor.fetchall():
                            try:
                                table_name = str(row[0]) if row[0] else None
                            except (UnicodeDecodeError, UnicodeEncodeError):
                                continue
                            
                            if table_name and not table_name.startswith('MSys'):
                                tables.append(table_name)
                    except Exception as last_resort_e:
                        logger.error(f"All table discovery methods failed: {last_resort_e}")
        else:  # SQLite
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting tables: {e}")
    return sorted(tables)

def get_table_info(conn, table_name):
    """Get column information for a table"""
    columns = []
    try:
        cursor = conn.cursor()
        if isinstance(conn, pyodbc.Connection):
            try:
                for column in cursor.columns(table=table_name):
                    # Handle potential encoding issues safely
                    try:
                        column_name = str(column.column_name) if column.column_name else 'Unknown'
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        column_name = f'Column_{len(columns) + 1}'
                    
                    try:
                        type_name = str(column.type_name) if column.type_name else 'Unknown'
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        type_name = 'Text'
                    
                    columns.append({
                        'name': column_name,
                        'type': type_name,
                        'size': getattr(column, 'column_size', None)
                    })
            except Exception as e:
                logger.warning(f"Error getting column metadata for table {table_name}: {e}")
                # Fallback: try to get basic column info using a different method
                try:
                    cursor.execute(f"SELECT TOP 1 * FROM [{table_name}]")
                    description = cursor.description
                    for i, col_desc in enumerate(description):
                        try:
                            column_name = str(col_desc[0]) if col_desc[0] else f'Column_{i + 1}'
                        except (UnicodeDecodeError, UnicodeEncodeError):
                            column_name = f'Column_{i + 1}'
                        
                        columns.append({
                            'name': column_name,
                            'type': 'Text',
                            'size': None
                        })
                except Exception as fallback_e:
                    logger.error(f"Fallback method also failed for table {table_name}: {fallback_e}")
                    # Last resort: create generic column info
                    columns = [{
                        'name': 'Column_1',
                        'type': 'Text',
                        'size': None
                    }]
        else:  # SQLite
            cursor.execute(f"PRAGMA table_info([{table_name}])")
            for col in cursor.fetchall():
                columns.append({
                    'name': col[1],
                    'type': col[2],
                    'size': None
                })
    except Exception as e:
        logger.error(f"Error getting table info: {e}")
        # Return at least one generic column to prevent complete failure
        if not columns:
            columns = [{
                'name': 'Data',
                'type': 'Text',
                'size': None
            }]
    return columns

def build_search_query(table_name, columns, search_term, search_columns, sort_column, sort_order, limit, offset):
    """Build optimized SQL query with search and pagination"""
    # Validate and escape table name
    table_name_escaped = f"[{table_name.replace(']', ']]')}]"
    
    # Base query - select only needed columns for better performance
    query = f"SELECT * FROM {table_name_escaped}"
    params = []
    
    # Add search conditions with optimized LIKE queries
    if search_term and columns:
        search_conditions = []
        if search_columns and search_columns != ['all']:
            # Search specific columns - validate column names
            valid_column_names = {c['name'] for c in columns}
            for col in search_columns:
                if col in valid_column_names:
                    # Escape column name to prevent injection
                    escaped_col = f"[{col.replace(']', ']]')}]"
                    search_conditions.append(f"UPPER(CAST({escaped_col} AS TEXT)) LIKE UPPER(?)")
                    params.append(f"%{search_term}%")
        else:
            # Search all text-compatible columns
            for col in columns:
                escaped_col = f"[{col['name'].replace(']', ']]')}]"
                # Only search text-like columns for better performance
                if col['type'] in ['Text', 'Memo', 'VARCHAR', 'CHAR', 'NVARCHAR', 'NCHAR', 'TEXT']:
                    search_conditions.append(f"UPPER(CAST({escaped_col} AS TEXT)) LIKE UPPER(?)")
                    params.append(f"%{search_term}%")
        
        if search_conditions:
            query += " WHERE " + " OR ".join(search_conditions)
    
    # Add sorting with validation
    if sort_column:
        valid_column_names = {c['name'] for c in columns}
        if sort_column in valid_column_names:
            escaped_sort_col = f"[{sort_column.replace(']', ']]')}]"
            query += f" ORDER BY {escaped_sort_col} {sort_order}"
    
    return query, params

def execute_paginated_query(conn, query, params, limit, offset):
    """Execute query with pagination handling for different database types"""
    cursor = conn.cursor()
    
    if isinstance(conn, pyodbc.Connection):
        # For Access databases, we'll use a more efficient approach
        # Use TOP clause for Access databases when possible
        if offset == 0:
            # First page - use TOP clause
            if "ORDER BY" in query.upper():
                # Insert TOP clause before ORDER BY
                order_index = query.upper().find("ORDER BY")
                base_query = query[:order_index].strip()
                order_clause = query[order_index:]
                
                # Check if it's a simple SELECT * query
                if base_query.upper().startswith("SELECT *"):
                    modified_query = base_query.replace("SELECT *", f"SELECT TOP {limit} *", 1) + " " + order_clause
                else:
                    # For complex queries, fall back to original method
                    modified_query = query
            else:
                # No ORDER BY clause
                if query.upper().startswith("SELECT *"):
                    modified_query = query.replace("SELECT *", f"SELECT TOP {limit} *", 1)
                else:
                    modified_query = query
            
            if modified_query != query:
                cursor.execute(modified_query, params)
                return cursor.fetchall(), cursor.description
        
        # Fallback method for Access - fetch and skip
        cursor.execute(query, params)
        
        # Skip to offset (more efficient with fetchmany)
        if offset > 0:
            # Use fetchmany to skip in chunks for better performance
            chunk_size = min(1000, offset)
            remaining = offset
            while remaining > 0:
                chunk = cursor.fetchmany(min(chunk_size, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        
        # Fetch the required rows
        rows = cursor.fetchmany(limit)
        return rows, cursor.description
    else:
        # SQLite supports LIMIT/OFFSET
        paginated_query = query + f" LIMIT {limit} OFFSET {offset}"
        cursor.execute(paginated_query, params)
        return cursor.fetchall(), cursor.description

def get_total_count(conn, table_name, columns, search_term, search_columns):
    """Get total count of rows (with search if applicable)"""
    query = f"SELECT COUNT(*) FROM [{table_name}]"
    params = []
    
    if search_term and columns:
        if search_columns and search_columns != ['all']:
            search_conditions = []
            for col in search_columns:
                if col in [c['name'] for c in columns]:
                    search_conditions.append(f"[{col}] LIKE ?")
                    params.append(f"%{search_term}%")
            if search_conditions:
                query += " WHERE " + " OR ".join(search_conditions)
        else:
            search_conditions = []
            for col in columns:
                search_conditions.append(f"[{col['name']}] LIKE ?")
                params.append(f"%{search_term}%")
            if search_conditions:
                query += " WHERE " + " OR ".join(search_conditions)
    
    cursor = conn.cursor()
    cursor.execute(query, params)
    return cursor.fetchone()[0]

def highlight_search_term(value, search_term):
    """Highlight search term in value"""
    if not search_term or not value:
        return value
    
    # Convert to string and escape HTML
    str_value = str(value)
    str_value = str_value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # Case-insensitive highlight
    pattern = re.compile(re.escape(search_term), re.IGNORECASE)
    return pattern.sub(lambda m: f'<mark>{m.group()}</mark>', str_value)

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/databases')
def list_databases():
    """Get list of all uploaded databases"""
    try:
        databases = get_all_databases()
        return jsonify({
            'success': True,
            'databases': databases,
            'admin_enabled': bool(DBVIEWER_ADMIN_TOKEN)
        })
    except Exception as e:
        logger.error(f"Error listing databases: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['POST'])
@limiter.limit("10 per minute")
def upload_file():
    """Handle file upload with enhanced security and error handling"""
    try:
        # Check if file is in request
        if 'file' not in request.files:
            log_security_event('missing_file', {'action': 'upload'})
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Enhanced file validation
        if not file or not allowed_file(file.filename):
            log_security_event('invalid_file_type', {
                'filename': file.filename,
                'content_type': file.content_type
            })
            return jsonify({'error': 'Invalid file type. Only .mdb, .accdb, .sqlite, and .db files are allowed'}), 400
        
        # Check file size before saving
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_UPLOAD_SIZE:
            log_security_event('file_too_large', {
                'filename': file.filename,
                'size': file_size
            })
            return jsonify({'error': f'File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)}MB'}), 400
        
        if file_size == 0:
            return jsonify({'error': 'Empty file not allowed'}), 400
        
        # Sanitize filename
        original_filename = file.filename
        filename = sanitize_filename(secure_filename(file.filename))
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        
        # Ensure upload directory exists
        upload_folder = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        
        filepath = os.path.join(upload_folder, filename)
        
        # Save file with error handling
        try:
            file.save(filepath)
            upload_logger.info(f"File saved: {filename} (original: {original_filename}, size: {file_size})")
        except Exception as e:
            upload_logger.error(f"Failed to save file {filename}: {e}")
            return jsonify({'error': 'Failed to save uploaded file'}), 500
        
        # Validate file content
        if not validate_file_content(filepath):
            upload_logger.warning(f"File content validation failed: {filename}")
            os.remove(filepath)
            log_security_event('invalid_file_content', {
                'filename': original_filename
            })
            return jsonify({'error': 'Invalid file format or corrupted file'}), 400
        
        # Get database info with error handling
        try:
            db_info = get_database_info(filepath)
            if not db_info:
                upload_logger.error(f"Failed to read database info: {filename}")
                os.remove(filepath)
                return jsonify({'error': 'Unable to read database file. File may be corrupted or password-protected'}), 500
            
            upload_logger.info(f"Database uploaded successfully: {filename}")
            return jsonify({
                'success': True,
                'database': db_info
            })
            
        except Exception as e:
            upload_logger.error(f"Database processing error for {filename}: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'error': f'Database processing failed: {str(e)}'}), 500
    
    except Exception as e:
        upload_logger.error(f"Unexpected upload error: {e}")
        return jsonify({'error': 'Upload failed due to server error'}), 500

# Decorator for admin token authentication
from functools import wraps

def admin_token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-Admin-Token')
        if not DBVIEWER_ADMIN_TOKEN: # If admin token is not configured on server
            security_logger.info(f"Admin action {f.__name__} attempted but DBVIEWER_ADMIN_TOKEN is not configured on the server.")
            return jsonify({'error': 'Admin operations are disabled. Contact administrator to enable admin token.'}), 501 # Not Implemented
        if not token or token != DBVIEWER_ADMIN_TOKEN:
            security_logger.warning(f"Unauthorized access attempt to {f.__name__} from {request.remote_addr}. Received token: '{token}'")
            return jsonify({'error': 'Unauthorized: Admin token required or invalid.'}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/database/<database_id>/tables')
@limiter.limit("30 per minute")
def get_tables_list(database_id):
    """Get list of tables for a specific database"""
    try:
        # Validate database_id format
        if not database_id or '..' in database_id or '/' in database_id:
            log_security_event('invalid_database_id', {'database_id': database_id})
            return jsonify({'error': 'Invalid database identifier'}), 400
        
        # Find database by ID (filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], database_id)
        if not os.path.exists(filepath) or not allowed_file(database_id):
            db_logger.warning(f"Database not found or invalid: {database_id}")
            return jsonify({'error': 'Database not found'}), 404
        
        conn = get_db_connection(filepath)
        tables = get_tables(conn)
        db_logger.info(f"Retrieved {len(tables)} tables for database: {database_id}")
        
        return jsonify({
            'success': True,
            'tables': tables,
            'database_id': database_id
        })
    except FileNotFoundError:
        return jsonify({'error': 'Database file not found'}), 404
    except ConnectionError as e:
        return jsonify({'error': f'Database connection failed: {str(e)}'}), 500
    except Exception as e:
        db_logger.error(f"Error getting tables for {database_id}: {e}")
        return jsonify({'error': 'Failed to retrieve database tables'}), 500

@app.route('/database/<database_id>/table/<table_name>')
@limiter.limit("50 per minute")
def view_table(database_id, table_name):
    """View table data with pagination and search - optimized for performance"""
    try:
        # Validate inputs to prevent injection
        if not database_id or '..' in database_id or '/' in database_id:
            log_security_event('invalid_database_id', {'database_id': database_id})
            return jsonify({'error': 'Invalid database identifier'}), 400
            
        if not table_name or len(table_name) > 128:
            log_security_event('invalid_table_name', {'table_name': table_name})
            return jsonify({'error': 'Invalid table name'}), 400
        
        # Find database by ID (filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], database_id)
        if not os.path.exists(filepath) or not allowed_file(database_id):
            return jsonify({'error': 'Database not found'}), 404
        
        # Get and validate parameters
        try:
            page = max(int(request.args.get('page', 1)), 1)
            per_page = min(max(int(request.args.get('per_page', 50)), 1), 1000)  # Increased max for exports
            sort_column = request.args.get('sort_column', '').strip()
            sort_order = request.args.get('sort_order', 'ASC').upper()
            search_term = request.args.get('search', '').strip()
            search_columns = request.args.getlist('search_columns')
        except (ValueError, TypeError) as e:
            return jsonify({'error': 'Invalid pagination parameters'}), 400
        
        # Validate sort order
        if sort_order not in ['ASC', 'DESC']:
            sort_order = 'ASC'
            
        # Limit search term length to prevent abuse
        if len(search_term) > 100:
            search_term = search_term[:100]
        
        conn = get_db_connection(filepath)
        
        # Get table info
        # First, validate table_name to prevent SQL injection
        all_tables = get_tables(conn)
        if table_name not in all_tables:
            logger.warning(f"Attempt to access non-existent or unauthorized table '{table_name}' in database '{database_id}'.")
            return jsonify({'error': f"Table '{table_name}' not found or access denied."}), 404

        columns = get_table_info(conn, table_name)
        if not columns:
            # This case should ideally be less frequent if table_name is validated against get_tables first,
            # but get_table_info might still fail for other reasons (e.g. permissions, corruption on a specific table).
            logger.error(f"Could not get column info for validated table '{table_name}' in database '{database_id}'.")
            return jsonify({'error': f"Could not retrieve column information for table '{table_name}'."}), 500
        
        # Calculate offset
        offset = (page - 1) * per_page
        
        # Build and execute query
        query, params = build_search_query(
            table_name, columns, search_term, search_columns,
            sort_column, sort_order, per_page, offset
        )
        
        rows, description = execute_paginated_query(conn, query, params, per_page, offset)
        
        # Get total count
        total_count = get_total_count(conn, table_name, columns, search_term, search_columns)
        
        # For filtered results, we need to get the actual filtered count
        if search_term:
            # Build count query with same WHERE clause
            count_query, count_params = build_search_query(
                table_name, columns, search_term, search_columns, '', '', 0, 0
            )
            count_query = count_query.replace("SELECT *", "SELECT COUNT(*)")
            
            # Remove ORDER BY from count query if present
            if "ORDER BY" in count_query.upper():
                order_index = count_query.upper().find("ORDER BY")
                count_query = count_query[:order_index].strip()
            
            count_cursor = conn.cursor()
            count_cursor.execute(count_query, count_params)
            filtered_count = count_cursor.fetchone()[0]
        else:
            filtered_count = total_count
        
        # Format results
        results = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(description):
                value = row[i]
                # Handle different data types with robust encoding
                if value is None:
                    display_value = 'NULL'
                elif isinstance(value, bytes):
                    try:
                        # Try to decode as UTF-8 first
                        display_value = value.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            # Try other common encodings
                            display_value = value.decode('latin-1')
                        except UnicodeDecodeError:
                            display_value = f'<Binary {len(value)} bytes>'
                elif isinstance(value, datetime):
                    display_value = value.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    try:
                        display_value = str(value)
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        try:
                            # Try repr for problematic values
                            display_value = repr(value)
                        except Exception:
                            display_value = '<Unable to display>'
                    except Exception:
                        display_value = '<Unable to display>'
                
                # Highlight search term
                if search_term:
                    display_value = highlight_search_term(display_value, search_term)
                
                row_dict[col[0]] = display_value
            results.append(row_dict)
        
        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page
        
        return jsonify({
            'success': True,
            'data': results,
            'columns': columns,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'filtered': filtered_count,
                'total_pages': total_pages
            },
            'sort': {
                'column': sort_column,
                'order': sort_order
            },
            'search': {
                'term': search_term,
                'columns': search_columns
            },
            'database_id': database_id
        })
        
    except Exception as e:
        logger.error(f"Error viewing table: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/database/<database_id>/delete', methods=['DELETE'])
@admin_token_required
def delete_database(database_id):
    """Delete a specific database"""
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], database_id)
        if not os.path.exists(filepath) or not allowed_file(database_id):
            return jsonify({'error': 'Database not found'}), 404
        
        # Close connection if cached
        with cache_lock:
            if filepath in connection_cache:
                conn = connection_cache.pop(filepath)
                try:
                    conn.close()
                except:
                    pass
        
        # Remove file
        os.remove(filepath)
        
        return jsonify({
            'success': True, 
            'message': f'Database {database_id} deleted successfully'
        })
    except Exception as e:
        logger.error(f"Delete error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/cleanup-all', methods=['POST'])
@admin_token_required
def cleanup_all():
    """Clean up all uploaded files (admin function)"""
    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        deleted_count = 0
        
        if os.path.exists(upload_folder):
            for filename in os.listdir(upload_folder):
                if allowed_file(filename):
                    filepath = os.path.join(upload_folder, filename)
                    if os.path.isfile(filepath):
                        # Close connection if cached
                        with cache_lock:
                            if filepath in connection_cache:
                                conn = connection_cache.pop(filepath)
                                try:
                                    conn.close()
                                except:
                                    pass
                        
                        os.remove(filepath)
                        deleted_count += 1
        
        return jsonify({
            'success': True, 
            'message': f'Cleaned up {deleted_count} database files'
        })
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 100MB.'}), 413

if __name__ == '__main__':
    # This block is for local development only.
    # In production, Gunicorn will serve the app.
    # For local testing with debug mode and threading:
    # Ensure FLASK_SECRET_KEY and DBVIEWER_ADMIN_TOKEN (if needed for testing admin features)
    # are set in your .env file or environment.
    # REDIS_URL can also be set if you want to test with Redis locally.
    logger.info("Starting Flask development server...")
    app.run(debug=True, threaded=True, host='0.0.0.0', port=os.environ.get('FLASK_RUN_PORT', 5000))