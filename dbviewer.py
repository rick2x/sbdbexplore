import os
import tempfile
import threading
import time
from datetime import datetime
from functools import lru_cache
from collections import OrderedDict
import logging
import json
import re
from dotenv import load_dotenv

from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect
import pyodbc
import sqlite3

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

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

# Unused database metadata cache - REMOVED
# database_metadata = {}
# metadata_lock = threading.Lock()

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

def get_db_connection(filepath):
    """Get database connection with caching"""
    with cache_lock:
        if filepath in connection_cache:
            # Move to end (LRU)
            connection_cache.move_to_end(filepath)
            return connection_cache[filepath]
        
        # Remove oldest if cache is full
        if len(connection_cache) >= MAX_CACHE_SIZE:
            oldest = next(iter(connection_cache))
            old_conn = connection_cache.pop(oldest)
            try:
                old_conn.close()
            except:
                pass
        
        # Create new connection
        file_ext = filepath.rsplit('.', 1)[-1].lower()
        conn = None

        if file_ext in ['mdb', 'accdb']:
            try:
                conn_str = get_connection_string(filepath)
                conn = pyodbc.connect(conn_str)
                try:
                    conn.setdecoding(pyodbc.SQL_CHAR, encoding='utf-8')
                    conn.setdecoding(pyodbc.SQL_WCHAR, encoding='utf-8')
                    conn.setencoding(encoding='utf-8')
                except Exception as encoding_error:
                    logger.warning(f"Could not set encoding for Access DB {filepath}: {encoding_error}")
                logger.info(f"Successfully connected to Access DB: {filepath}")
            except Exception as e:
                logger.error(f"Failed to connect to Access DB {filepath} with pyodbc: {e}")
                raise 
        elif file_ext in ['sqlite', 'db']:
            try:
                conn = sqlite3.connect(filepath, check_same_thread=False) 
                logger.info(f"Successfully connected to SQLite DB: {filepath}")
            except Exception as e:
                logger.error(f"Failed to connect to SQLite DB {filepath}: {e}")
                raise
        else:
            logger.error(f"Unsupported database type: {file_ext} for file {filepath}")
            raise ValueError(f"Unsupported database type: {file_ext}")

        if conn:
            connection_cache[filepath] = conn
            return conn
        else:
            # This path should ideally not be reached if exceptions are raised above
            raise ConnectionError(f"Failed to establish database connection for {filepath}")

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
    # Base query
    query = f"SELECT * FROM [{table_name}]"
    params = []
    
    # Add search conditions
    if search_term and columns:
        if search_columns and search_columns != ['all']:
            # Search specific columns
            search_conditions = []
            for col in search_columns:
                if col in [c['name'] for c in columns]:
                    search_conditions.append(f"[{col}] LIKE ?")
                    params.append(f"%{search_term}%")
            if search_conditions:
                query += " WHERE " + " OR ".join(search_conditions)
        else:
            # Search all columns
            search_conditions = []
            for col in columns:
                search_conditions.append(f"[{col['name']}] LIKE ?")
                params.append(f"%{search_term}%")
            if search_conditions:
                query += " WHERE " + " OR ".join(search_conditions)
    
    # Add sorting
    if sort_column and sort_column in [c['name'] for c in columns]:
        query += f" ORDER BY [{sort_column}] {sort_order}"
    
    # Add pagination (different syntax for Access vs SQLite)
    # For Access, we'll handle pagination differently
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
            'databases': databases
        })
    except Exception as e:
        logger.error(f"Error listing databases: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            file.save(filepath)
            
            # Get database info
            db_info = get_database_info(filepath)
            if not db_info:
                if os.path.exists(filepath):
                    os.remove(filepath)
                return jsonify({'error': 'Failed to read database file'}), 500
            
            return jsonify({
                'success': True,
                'database': db_info
            })
        except Exception as e:
            logger.error(f"Upload error: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Invalid file type'}), 400

# Decorator for admin token authentication
from functools import wraps

def admin_token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-Admin-Token')
        if not DBVIEWER_ADMIN_TOKEN: # If admin token is not configured on server
            logger.error(f"Admin action {f.__name__} attempted but DBVIEWER_ADMIN_TOKEN is not configured on the server.")
            return jsonify({'error': 'Action not configured. Admin token not set up on server.'}), 501 # Not Implemented
        if not token or token != DBVIEWER_ADMIN_TOKEN:
            logger.warning(f"Unauthorized access attempt to {f.__name__} without valid admin token. Received token: '{token}'")
            return jsonify({'error': 'Unauthorized: Admin token required or invalid.'}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/database/<database_id>/tables')
def get_tables_list(database_id):
    """Get list of tables for a specific database"""
    try:
        # Find database by ID (filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], database_id)
        if not os.path.exists(filepath) or not allowed_file(database_id):
            return jsonify({'error': 'Database not found'}), 404
        
        conn = get_db_connection(filepath)
        tables = get_tables(conn)
        return jsonify({
            'success': True,
            'tables': tables,
            'database_id': database_id
        })
    except Exception as e:
        logger.error(f"Error getting tables: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/database/<database_id>/table/<table_name>')
def view_table(database_id, table_name):
    """View table data with pagination and search"""
    try:
        # Find database by ID (filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], database_id)
        if not os.path.exists(filepath) or not allowed_file(database_id):
            return jsonify({'error': 'Database not found'}), 404
        
        # Get parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        sort_column = request.args.get('sort_column', '')
        sort_order = request.args.get('sort_order', 'ASC')
        search_term = request.args.get('search', '')
        search_columns = request.args.getlist('search_columns')
        
        # Validate parameters
        per_page = min(max(per_page, 1), 500)
        page = max(page, 1)
        sort_order = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'
        
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
    # Run with threading for better performance
    app.run(debug=True, threaded=True, host='0.0.0.0', port=5000)