"""
Complete Production-Ready Conversational Timesheet Bot
with Weekly Copy Feature and Project Code Validation

Enhanced Features:
- Project code validation with predefined codes
- Weekly timesheet copying (Monday to Friday)
- Conflict detection for existing timesheets
- Override functionality with confirmation
- Advanced conversational flow handling missing details
- Draft preview for weekly submissions
- Multi-user authentication with persistent sessions
- Comprehensive audit logging and history

Requirements:
pip install ollama pyodbc gradio bcrypt pandas

Usage:
python enhanced_weekly_timesheet_bot.py
"""

import ollama
import gradio as gr
import json
import datetime
import re
import bcrypt
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Tuple, Any
import pyodbc
from contextlib import contextmanager
import random
import uuid
import calendar

@dataclass
class TimesheetEntry:
    id: Optional[int] = None
    date: str = ""
    hours: float = 0.0
    system: str = ""
    project_code: str = ""
    task: str = ""
    submitted_at: str = ""
    user_id: str = ""
    table_type: str = ""
    validation_status: str = "valid"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class ProjectCode:
    id: Optional[int] = None
    code: str = ""
    description: str = ""
    table_type: str = ""
    is_active: bool = True
    created_at: str = ""

@dataclass
class User:
    id: Optional[int] = None
    username: str = ""
    email: str = ""
    password_hash: str = ""
    role: str = "user"
    created_at: str = ""
    last_login: Optional[str] = None
    is_active: bool = True

@dataclass
class WeeklyTimesheetBatch:
    table_type: str = ""
    hours: float = 0.0
    system: str = ""
    project_code: str = ""
    task: str = ""
    start_date: str = ""
    end_date: str = ""
    dates: List[str] = None
    existing_entries: List[TimesheetEntry] = None
    conflicts: List[str] = None

class DatabaseManager:
    def __init__(self, connection_string=None):
        self.connection_string = connection_string or (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=localhost;"
            "DATABASE=TimesheetDB;"
            "Trusted_Connection=yes;"
        )
        self.init_database()

    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = pyodbc.connect(self.connection_string)
            conn.autocommit = False
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()

    def init_database(self):
        """Initialize all database tables and insert sample project codes"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Users table
                cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='users' AND xtype='U')
                BEGIN
                    CREATE TABLE users (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        username NVARCHAR(50) UNIQUE NOT NULL,
                        email NVARCHAR(100) UNIQUE NOT NULL,
                        password_hash NVARCHAR(256) NOT NULL,
                        role NVARCHAR(20) DEFAULT 'user',
                        created_at DATETIME2 DEFAULT GETDATE(),
                        last_login DATETIME2,
                        is_active BIT DEFAULT 1
                    );
                    CREATE INDEX IX_users_username ON users(username);
                END
                """)
                
                # Project codes table
                cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='project_codes' AND xtype='U')
                BEGIN
                    CREATE TABLE project_codes (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        code NVARCHAR(20) UNIQUE NOT NULL,
                        description NVARCHAR(200) NOT NULL,
                        table_type NVARCHAR(20) NOT NULL,
                        is_active BIT DEFAULT 1,
                        created_at DATETIME2 DEFAULT GETDATE()
                    );
                    CREATE INDEX IX_project_codes_table_type ON project_codes(table_type, is_active);
                END
                """)
                
                # Mars timesheet table
                cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Mars_timesheet' AND xtype='U')
                BEGIN
                    CREATE TABLE Mars_timesheet (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        date DATE NOT NULL,
                        hours DECIMAL(5,2) NOT NULL CHECK (hours > 0 AND hours <= 24),
                        system NVARCHAR(100) NOT NULL,
                        project_code NVARCHAR(20) NOT NULL,
                        task NVARCHAR(1000) NOT NULL,
                        submitted_at DATETIME2 NOT NULL,
                        user_id NVARCHAR(50) NOT NULL,
                        validation_status NVARCHAR(20) DEFAULT 'valid',
                        created_at DATETIME2 DEFAULT GETDATE(),
                        updated_at DATETIME2 DEFAULT GETDATE(),
                        UNIQUE(user_id, date)
                    );
                    CREATE INDEX IX_Mars_user_date ON Mars_timesheet(user_id, date DESC);
                    CREATE INDEX IX_Mars_project_code ON Mars_timesheet(project_code);
                END
                """)
                
                # Oracle timesheet table  
                cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Oracle_timesheet' AND xtype='U')
                BEGIN
                    CREATE TABLE Oracle_timesheet (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        date DATE NOT NULL,
                        hours DECIMAL(5,2) NOT NULL CHECK (hours > 0 AND hours <= 24),
                        system NVARCHAR(100) NOT NULL,
                        project_code NVARCHAR(20) NOT NULL,
                        task NVARCHAR(1000) NOT NULL,
                        submitted_at DATETIME2 NOT NULL,
                        user_id NVARCHAR(50) NOT NULL,
                        validation_status NVARCHAR(20) DEFAULT 'valid',
                        created_at DATETIME2 DEFAULT GETDATE(),
                        updated_at DATETIME2 DEFAULT GETDATE(),
                        UNIQUE(user_id, date)
                    );
                    CREATE INDEX IX_Oracle_user_date ON Oracle_timesheet(user_id, date DESC);
                    CREATE INDEX IX_Oracle_project_code ON Oracle_timesheet(project_code);
                END
                """)
                
                # Audit log table
                cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='audit_log' AND xtype='U')
                BEGIN
                    CREATE TABLE audit_log (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        user_id NVARCHAR(50) NOT NULL,
                        action NVARCHAR(50) NOT NULL,
                        table_name NVARCHAR(50) NOT NULL,
                        record_id INT,
                        old_values NVARCHAR(MAX),
                        new_values NVARCHAR(MAX),
                        timestamp DATETIME2 DEFAULT GETDATE(),
                        ip_address NVARCHAR(45),
                        user_agent NVARCHAR(500)
                    );
                    CREATE INDEX IX_audit_timestamp ON audit_log(timestamp DESC);
                    CREATE INDEX IX_audit_user ON audit_log(user_id, timestamp DESC);
                END
                """)
                
                # Sessions table
                cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='user_sessions' AND xtype='U')
                BEGIN
                    CREATE TABLE user_sessions (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        session_id NVARCHAR(100) UNIQUE NOT NULL,
                        user_id NVARCHAR(50) NOT NULL,
                        conversation_state NVARCHAR(50) DEFAULT 'greeting',
                        current_entry NVARCHAR(MAX) DEFAULT '{}',
                        selected_table NVARCHAR(20) DEFAULT '',
                        conversation_history NVARCHAR(MAX) DEFAULT '[]',
                        weekly_batch NVARCHAR(MAX) DEFAULT '{}',
                        created_at DATETIME2 DEFAULT GETDATE(),
                        updated_at DATETIME2 DEFAULT GETDATE(),
                        expires_at DATETIME2 NOT NULL
                    );
                    CREATE INDEX IX_sessions_session_id ON user_sessions(session_id);
                    CREATE INDEX IX_sessions_expires ON user_sessions(expires_at);
                END
                """)
                
                conn.commit()
                
                # Create default admin user and sample project codes
                self._create_default_data(cursor, conn)
                
        except Exception as e:
            print(f"Database initialization error: {e}")
            raise

    def _create_default_data(self, cursor, conn):
        """Create default admin user and sample project codes"""
        try:
            # Create default admin if not exists
            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            if cursor.fetchone()[0] == 0:
                admin_password_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                cursor.execute("""
                    INSERT INTO users (username, email, password_hash, role)
                    VALUES (?, ?, ?, ?)
                """, ("admin", "admin@company.com", admin_password_hash, "admin"))
                print("✅ Default admin user created (admin/admin123)")
            
            # Create sample user
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'user1'")
            if cursor.fetchone()[0] == 0:
                user_password_hash = bcrypt.hashpw("user123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                cursor.execute("""
                    INSERT INTO users (username, email, password_hash, role)
                    VALUES (?, ?, ?, ?)
                """, ("user1", "user1@company.com", user_password_hash, "user"))
                print("✅ Sample user created (user1/user123)")
            
            # Create sample project codes if not exists
            cursor.execute("SELECT COUNT(*) FROM project_codes")
            if cursor.fetchone()[0] == 0:
                project_codes = [
                    # Mars projects
                    ("MARS001", "Mars Rover Navigation System Development", "Mars"),
                    ("MARS002", "Mars Habitat Life Support Engineering", "Mars"),
                    ("MARS003", "Mars Communication Array Infrastructure", "Mars"),
                    ("MARS004", "Mars Surface Exploration Mission Planning", "Mars"),
                    ("MARS005", "Mars Sample Collection System Design", "Mars"),
                    
                    # Oracle projects  
                    ("ORA100", "Enterprise Database Performance Optimization", "Oracle"),
                    ("ORA101", "Oracle Cloud Infrastructure Migration", "Oracle"),
                    ("ORA102", "Data Warehouse ETL Process Enhancement", "Oracle"),
                    ("ORA103", "Oracle Security Framework Implementation", "Oracle"),
                    ("ORA104", "Database Backup and Recovery Strategy", "Oracle")
                ]
                
                for code, desc, table_type in project_codes:
                    cursor.execute("""
                        INSERT INTO project_codes (code, description, table_type)
                        VALUES (?, ?, ?)
                    """, (code, desc, table_type))
                
                print(f"✅ {len(project_codes)} sample project codes created")
            
            conn.commit()
            
        except Exception as e:
            print(f"Error creating default data: {e}")

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user credentials"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, username, email, password_hash, role, created_at, last_login, is_active
                    FROM users WHERE username = ? AND is_active = 1
                """, (username,))
                
                row = cursor.fetchone()
                if row and bcrypt.checkpw(password.encode('utf-8'), row[3].encode('utf-8')):
                    # Update last login
                    cursor.execute("UPDATE users SET last_login = GETDATE() WHERE id = ?", (row[0],))
                    conn.commit()
                    
                    return User(
                        id=row[0], username=row[1], email=row[2], password_hash=row[3],
                        role=row[4], created_at=str(row[5]), last_login=str(row[6]) if row[6] else None,
                        is_active=bool(row[7])
                    )
        except Exception as e:
            print(f"Authentication error: {e}")
        
        return None

    def create_user_session(self, user_id: str) -> str:
        """Create new user session"""
        session_id = str(uuid.uuid4())
        expires_at = datetime.datetime.now() + datetime.timedelta(hours=8)
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_sessions (session_id, user_id, expires_at)
                    VALUES (?, ?, ?)
                """, (session_id, user_id, expires_at))
                conn.commit()
                return session_id
        except Exception as e:
            print(f"Session creation error: {e}")
            return ""

    def get_user_session(self, session_id: str) -> Optional[Dict]:
        """Get user session data"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id, conversation_state, current_entry, selected_table, 
                           conversation_history, weekly_batch, expires_at
                    FROM user_sessions 
                    WHERE session_id = ? AND expires_at > GETDATE()
                """, (session_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'user_id': row[0],
                        'conversation_state': row[1] or 'greeting',
                        'current_entry': json.loads(row[2]) if row[2] else {},
                        'selected_table': row[3] or '',
                        'conversation_history': json.loads(row[4]) if row[4] else [],
                        'weekly_batch': json.loads(row[5]) if row[5] else {},
                        'expires_at': row[6]
                    }
        except Exception as e:
            print(f"Session retrieval error: {e}")
        
        return None

    def update_user_session(self, session_id: str, conversation_state: str, 
                           current_entry: Dict, selected_table: str, conversation_history: List,
                           weekly_batch: Dict = None):
        """Update user session data"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE user_sessions 
                    SET conversation_state = ?, current_entry = ?, selected_table = ?, 
                        conversation_history = ?, weekly_batch = ?, updated_at = GETDATE(),
                        expires_at = DATEADD(hour, 8, GETDATE())
                    WHERE session_id = ?
                """, (
                    conversation_state,
                    json.dumps(current_entry),
                    selected_table,
                    json.dumps(conversation_history),
                    json.dumps(weekly_batch or {}),
                    session_id
                ))
                conn.commit()
        except Exception as e:
            print(f"Session update error: {e}")

    def get_project_codes(self, table_type: str) -> List[ProjectCode]:
        """Get active project codes for a table type"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, code, description, table_type, is_active, created_at
                    FROM project_codes 
                    WHERE table_type = ? AND is_active = 1
                    ORDER BY code
                """, (table_type,))
                
                rows = cursor.fetchall()
                return [ProjectCode(
                    id=row[0], code=row[1], description=row[2], 
                    table_type=row[3], is_active=bool(row[4]), created_at=str(row[5])
                ) for row in rows]
        except Exception as e:
            print(f"Error fetching project codes: {e}")
            return []

    def is_valid_project_code(self, table_type: str, project_code: str) -> bool:
        """Check if project code is valid for the table type"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM project_codes 
                    WHERE table_type = ? AND code = ? AND is_active = 1
                """, (table_type, project_code.upper()))
                
                return cursor.fetchone()[0] > 0
        except Exception as e:
            print(f"Error validating project code: {e}")
            return False

    def check_existing_timesheets(self, user_id: str, table_type: str, dates: List[str]) -> List[TimesheetEntry]:
        """Check for existing timesheets for given dates"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                table_name = f"{table_type}_timesheet"
                
                placeholders = ','.join(['?' for _ in dates])
                query = f"""
                    SELECT id, date, hours, system, project_code, task, submitted_at, 
                           validation_status, created_at
                    FROM {table_name}
                    WHERE user_id = ? AND date IN ({placeholders})
                    ORDER BY date
                """
                
                cursor.execute(query, [user_id] + dates)
                rows = cursor.fetchall()
                
                existing = []
                for row in rows:
                    existing.append(TimesheetEntry(
                        id=row[0], date=str(row[1]), hours=float(row[2]),
                        system=row[3], project_code=row[4], task=row[5],
                        submitted_at=str(row[6]), user_id=user_id, table_type=table_type,
                        validation_status=row[7], created_at=str(row[8])
                    ))
                
                return existing
                
        except Exception as e:
            print(f"Error checking existing timesheets: {e}")
            return []

    def save_timesheet(self, entry: TimesheetEntry, update_existing: bool = False) -> Tuple[bool, Optional[int]]:
        """Save timesheet with audit logging"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                table_name = f"{entry.table_type}_timesheet"
                
                if update_existing:
                    # Update existing record
                    update_sql = f"""
                    UPDATE {table_name} 
                    SET hours = ?, system = ?, project_code = ?, task = ?, 
                        submitted_at = ?, validation_status = ?, updated_at = GETDATE()
                    WHERE user_id = ? AND date = ?
                    """
                    
                    cursor.execute(update_sql, (
                        entry.hours, entry.system, entry.project_code, entry.task,
                        entry.submitted_at, entry.validation_status, entry.user_id, entry.date
                    ))
                    
                    # Get updated record ID
                    cursor.execute(f"SELECT id FROM {table_name} WHERE user_id = ? AND date = ?", 
                                 (entry.user_id, entry.date))
                    record_id = cursor.fetchone()[0]
                    
                    action = "UPDATE"
                else:
                    # Insert new record
                    insert_sql = f"""
                    INSERT INTO {table_name} (date, hours, system, project_code, task, 
                                            submitted_at, user_id, validation_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    
                    cursor.execute(insert_sql, (
                        entry.date, entry.hours, entry.system, entry.project_code,
                        entry.task, entry.submitted_at, entry.user_id, entry.validation_status
                    ))
                    
                    # Get inserted record ID
                    cursor.execute("SELECT @@IDENTITY")
                    record_id = cursor.fetchone()[0]
                    
                    action = "INSERT"
                
                conn.commit()
                
                # Log audit event
                self.log_audit_event(
                    user_id=entry.user_id,
                    action=action,
                    table_name=table_name,
                    record_id=record_id,
                    new_values=asdict(entry)
                )
                
                return True, record_id
        except Exception as e:
            print(f"Save timesheet error: {e}")
            return False, None

    def save_weekly_timesheets(self, entries: List[TimesheetEntry], update_existing: bool = False) -> Tuple[bool, List[int]]:
        """Save multiple timesheet entries for weekly batch"""
        record_ids = []
        try:
            for entry in entries:
                success, record_id = self.save_timesheet(entry, update_existing)
                if success and record_id:
                    record_ids.append(record_id)
                else:
                    # If any entry fails, return failure
                    return False, record_ids
            
            return True, record_ids
        except Exception as e:
            print(f"Weekly timesheet save error: {e}")
            return False, record_ids

    def log_audit_event(self, user_id: str, action: str, table_name: str, 
                       record_id: Optional[int] = None, old_values: Optional[Dict] = None,
                       new_values: Optional[Dict] = None):
        """Log audit event"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO audit_log (user_id, action, table_name, record_id, 
                                         old_values, new_values)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    user_id, action, table_name, record_id,
                    json.dumps(old_values) if old_values else None,
                    json.dumps(new_values) if new_values else None
                ))
                conn.commit()
        except Exception as e:
            print(f"Audit logging error: {e}")

    def load_timesheets_paginated(self, user_id: str, table_type: str = "Mars", 
                                page: int = 1, per_page: int = 10,
                                start_date: Optional[str] = None, 
                                end_date: Optional[str] = None) -> Dict:
        """Load paginated timesheets with filtering"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                table_name = f"{table_type}_timesheet"
                
                # Build WHERE clause
                where_conditions = ["user_id = ?"]
                params = [user_id]
                
                if start_date:
                    where_conditions.append("date >= ?")
                    params.append(start_date)
                
                if end_date:
                    where_conditions.append("date <= ?")
                    params.append(end_date)
                
                where_clause = " AND ".join(where_conditions)
                
                # Get total count
                count_sql = f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}"
                cursor.execute(count_sql, params)
                total_count = cursor.fetchone()[0]
                
                # Get paginated results
                offset = (page - 1) * per_page
                select_sql = f"""
                SELECT id, date, hours, system, project_code, task, submitted_at, 
                       validation_status, created_at
                FROM {table_name} 
                WHERE {where_clause}
                ORDER BY submitted_at DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """
                
                cursor.execute(select_sql, params + [offset, per_page])
                rows = cursor.fetchall()
                
                timesheets = []
                for row in rows:
                    timesheets.append(TimesheetEntry(
                        id=row[0], date=str(row[1]), hours=float(row[2]),
                        system=row[3], project_code=row[4], task=row[5],
                        submitted_at=str(row[6]), user_id=user_id, table_type=table_type,
                        validation_status=row[7], created_at=str(row[8])
                    ))
                
                return {
                    'timesheets': timesheets,
                    'total_count': total_count,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': (total_count + per_page - 1) // per_page
                }
                
        except Exception as e:
            print(f"Load timesheets error: {e}")
            return {'timesheets': [], 'total_count': 0, 'page': 1, 'per_page': per_page, 'total_pages': 0}

class WeeklyTimesheetHelper:
    """Helper class for weekly timesheet operations"""
    
    @staticmethod
    def get_week_dates(date_str: str) -> List[str]:
        """Get Monday to Friday dates for the week containing the given date"""
        try:
            date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            # Get Monday of the week (weekday 0 = Monday)
            monday = date_obj - datetime.timedelta(days=date_obj.weekday())
            
            # Generate Monday to Friday
            week_dates = []
            for i in range(5):  # Monday to Friday
                week_dates.append((monday + datetime.timedelta(days=i)).strftime('%Y-%m-%d'))
            
            return week_dates
        except ValueError:
            return []
    
    @staticmethod
    def parse_date_from_input(user_input: str) -> Optional[str]:
        """Parse date from user input"""
        # Look for date patterns
        date_patterns = [
            r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
            r'(\d{2}/\d{2}/\d{4})',  # MM/DD/YYYY
            r'(\d{2}-\d{2}-\d{4})',  # MM-DD-YYYY
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, user_input)
            if match:
                date_str = match.group(1)
                try:
                    # Convert to standard format
                    if '/' in date_str:
                        date_obj = datetime.datetime.strptime(date_str, '%m/%d/%Y')
                    elif '-' in date_str and len(date_str.split('-')[0]) == 2:
                        date_obj = datetime.datetime.strptime(date_str, '%m-%d-%Y')
                    else:
                        date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                    
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    continue
        
        return None

class ConversationalTimesheetBot:
    """Enhanced conversational bot with weekly timesheet functionality"""
    
    def __init__(self, db: DatabaseManager, model_name: str = "llama3.2:1b"):
        self.db = db
        self.model_name = model_name
        self.required_fields = ['table_type', 'hours', 'system', 'project_code', 'task']
        self.max_daily_hours = 12.0
        self.weekly_helper = WeeklyTimesheetHelper()
        
        # Conversational responses
        self.greetings = [
            "Hey there! 👋", "Hello! 😊", "Hi! Good to see you!", "Hey! Ready to log some hours?",
            "What's up! 🙌", "Hello there!", "Hi! Hope you're having a great day!"
        ]
        
        self.positive_responses = [
            "Awesome!", "Perfect!", "Great!", "Excellent!", "Nice!", "Sweet!",
            "Got it!", "Love it!", "Fantastic!", "Cool!", "Amazing!"
        ]
        
        try:
            ollama.chat(model=self.model_name, messages=[{"role": "user", "content": "test"}])
            print(f"✅ Ollama {self.model_name} is ready")
        except Exception as e:
            print(f"⚠️ Ollama connection issue: {e}")

    def extract_hours_naturally(self, text: str) -> Optional[float]:
        """Extract hours from natural language"""
        text_lower = text.lower()
        
        # Number word mappings
        word_numbers = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'eleven': 11, 'twelve': 12
        }
        
        # Replace word numbers
        for word, num in word_numbers.items():
            if word in text_lower:
                text_lower = text_lower.replace(word, str(num))
        
        # Patterns for hours
        patterns = [
            r'(\d+\.?\d*)\s*(?:and\s*(?:a\s*)?half|\.5)',  # "8 and a half"
            r'(\d+\.?\d*)\s*(?:hours?|hrs?|h)',  # "8 hours"
            r'about\s*(\d+\.?\d*)',  # "about 8"
            r'around\s*(\d+\.?\d*)',  # "around 7"
            r'(\d+\.?\d*)',  # just numbers
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    hours = float(match.group(1))
                    if 'and a half' in text_lower or 'and half' in text_lower:
                        hours += 0.5
                    if 0 < hours <= 24:
                        return hours
                except ValueError:
                    continue
        
        return None

    def detect_table_preference(self, text: str) -> Optional[str]:
        """Detect Mars or Oracle preference"""
        text_lower = text.lower()
        
        mars_keywords = ['mars', 'space', 'rover', 'planet', 'mission', 'spacecraft']
        oracle_keywords = ['oracle', 'database', 'sql', 'db', 'data', 'query']
        
        mars_score = sum(1 for keyword in mars_keywords if keyword in text_lower)
        oracle_score = sum(1 for keyword in oracle_keywords if keyword in text_lower)
        
        if mars_score > oracle_score or 'mars' in text_lower:
            return "Mars"
        elif oracle_score > mars_score or 'oracle' in text_lower:
            return "Oracle"
        
        return None

    def extract_system_info(self, text: str) -> Optional[str]:
        """Extract system information"""
        text = text.strip()
        
        system_map = {
            'jira': 'Jira', 'github': 'GitHub', 'git': 'GitHub',
            'sql': 'SQL Developer', 'database': 'Database',
            'oracle': 'Oracle', 'mysql': 'MySQL', 'postgres': 'PostgreSQL',
            'slack': 'Slack', 'teams': 'Microsoft Teams',
            'vs code': 'VS Code', 'visual studio': 'Visual Studio'
        }
        
        text_lower = text.lower()
        for key, value in system_map.items():
            if key in text_lower:
                return value
        
        return text.title() if len(text) > 1 else None

    def detect_project_code(self, text: str, table_type: str) -> Optional[str]:
        """Detect project code in user input"""
        if not table_type:
            return None
            
        project_codes = self.db.get_project_codes(table_type)
        text_upper = text.upper()
        
        for project_code in project_codes:
            if project_code.code in text_upper:
                return project_code.code
        
        return None

    def detect_weekly_request(self, text: str) -> bool:
        """Detect if user wants weekly timesheet functionality"""
        weekly_keywords = [
            'week', 'weekly', 'monday to friday', 'whole week', 'entire week',
            'copy for week', 'same timesheet for week', 'fill week', 'weekly copy'
        ]
        
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in weekly_keywords)

    def process_conversation(self, user_input: str, session_id: str, history: List[Tuple[str, str]]) -> Tuple[str, List[Tuple[str, str]]]:
        """Main conversation processing with weekly functionality"""
        
        if not user_input.strip():
            return "", history
        
        # Get session data
        session_data = self.db.get_user_session(session_id)
        if not session_data:
            response = "❌ Session expired. Please log in again."
            history.append((user_input, response))
            return "", history
        
        conversation_state = session_data['conversation_state']
        current_entry = session_data['current_entry']
        selected_table = session_data['selected_table']
        conversation_history = session_data['conversation_history']
        weekly_batch = session_data['weekly_batch']
        user_id = session_data['user_id']
        
        user_input_clean = user_input.strip()
        user_input_lower = user_input_clean.lower()
        
        # Handle special commands
        if any(word in user_input_lower for word in ['reset', 'start over', 'new timesheet']):
            conversation_state = "greeting"
            current_entry = {}
            selected_table = ""
            weekly_batch = {}
            conversation_history = []
            response = "🔄 Starting fresh! Are you logging Mars (🚀) or Oracle (🔮) time today?\n\n💡 **Tip:** You can also say 'copy for the whole week' to fill Monday-Friday with the same timesheet!"
            
            self.db.update_user_session(session_id, conversation_state, current_entry, selected_table, conversation_history, weekly_batch)
            history.append((user_input, response))
            return "", history
        
        # Handle project code requests
        if any(phrase in user_input_lower for phrase in ['show my project code', 'list project codes', 'what project codes', 'project codes', 'show codes']):
            if not selected_table:
                response = "Please first tell me if you're working on Mars (🚀) or Oracle (🔮) projects, then I can show you the available project codes."
            else:
                project_codes = self.db.get_project_codes(selected_table)
                if project_codes:
                    code_list = "\n".join([f"• **{pc.code}**: {pc.description}" for pc in project_codes])
                    response = f"📋 **Available {selected_table} Project Codes:**\n\n{code_list}\n\nJust mention the code you want to use!"
                else:
                    response = f"No {selected_table} project codes found. Please contact your administrator."
            
            history.append((user_input, response))
            return "", history
        
        # Handle weekly timesheet requests
        if self.detect_weekly_request(user_input) or conversation_state.startswith('weekly_'):
            return self.handle_weekly_conversation(user_input, session_data, history, session_id)
        
        # Regular single timesheet flow
        return self.handle_single_timesheet_conversation(user_input, session_data, history, session_id)

    def handle_weekly_conversation(self, user_input: str, session_data: Dict, history: List[Tuple[str, str]], session_id: str) -> Tuple[str, List[Tuple[str, str]]]:
        """Handle weekly timesheet conversation flow"""
        
        conversation_state = session_data['conversation_state']
        current_entry = session_data['current_entry']
        selected_table = session_data['selected_table']
        weekly_batch = session_data['weekly_batch']
        user_id = session_data['user_id']
        user_input_clean = user_input.strip()
        user_input_lower = user_input_clean.lower()
        
        # Initialize weekly batch if needed
        if not weekly_batch:
            weekly_batch = WeeklyTimesheetBatch().__dict__
        
        # Extract information from user input
        if not selected_table:
            table_pref = self.detect_table_preference(user_input)
            if table_pref:
                selected_table = table_pref
                weekly_batch['table_type'] = table_pref
        
        if not weekly_batch.get('hours'):
            hours = self.extract_hours_naturally(user_input)
            if hours:
                weekly_batch['hours'] = hours
        
        if not weekly_batch.get('system'):
            system = self.extract_system_info(user_input)
            if system:
                weekly_batch['system'] = system
        
        if not weekly_batch.get('project_code') and selected_table:
            project_code = self.detect_project_code(user_input, selected_table)
            if project_code:
                weekly_batch['project_code'] = project_code
        
        if not weekly_batch.get('task') and len(user_input_clean) > 10:
            if not any(field in user_input_lower for field in ['mars', 'oracle', 'hours', 'hour', 'week', 'monday', 'friday']):
                weekly_batch['task'] = user_input_clean
        
        # Handle date specification
        if not weekly_batch.get('start_date'):
            parsed_date = self.weekly_helper.parse_date_from_input(user_input)
            if parsed_date:
                week_dates = self.weekly_helper.get_week_dates(parsed_date)
                if week_dates:
                    weekly_batch['start_date'] = week_dates[0]
                    weekly_batch['end_date'] = week_dates[4]
                    weekly_batch['dates'] = week_dates
            elif conversation_state == 'greeting' or conversation_state == 'weekly_start':
                # Default to current week
                today = datetime.date.today()
                week_dates = self.weekly_helper.get_week_dates(today.strftime('%Y-%m-%d'))
                weekly_batch['start_date'] = week_dates[0]
                weekly_batch['end_date'] = week_dates[4]
                weekly_batch['dates'] = week_dates
        
        # State transitions
        if conversation_state == 'greeting' or conversation_state == 'weekly_start':
            conversation_state = 'weekly_gathering'
        
        # Check for missing required fields
        required_weekly_fields = ['table_type', 'hours', 'system', 'project_code', 'task', 'dates']
        missing_fields = [field for field in required_weekly_fields if not weekly_batch.get(field)]
        
        if missing_fields:
            # Ask for the first missing field
            field = missing_fields[0]
            
            if field == 'table_type':
                response = f"{random.choice(self.greetings)} I see you want to fill a weekly timesheet!\n\nAre you logging time for:\n🚀 **Mars projects** (space & exploration)\n🔮 **Oracle projects** (database & enterprise)\n\nJust say 'Mars' or 'Oracle'!"
            
            elif field == 'hours':
                response = f"How many hours per day did you work on {selected_table} projects? (This will be copied to Monday-Friday)"
            
            elif field == 'system':
                response = f"What tools or systems did you use for your {selected_table} work this week? (e.g., Jira, GitHub, SQL Developer)"
            
            elif field == 'project_code':
                project_codes = self.db.get_project_codes(selected_table)
                if project_codes:
                    code_examples = ", ".join([pc.code for pc in project_codes[:3]])
                    response = f"Which {selected_table} project code were you working on this week? (e.g., {code_examples})\n\nIf you don't know the codes, just ask me to 'show my project codes'!"
                else:
                    response = f"Please provide the {selected_table} project code for this weekly timesheet."
            
            elif field == 'task':
                response = f"Please describe what you worked on for project {weekly_batch.get('project_code', 'code')} this week. This description will be used for all days."
            
            elif field == 'dates':
                response = "Which week do you want to fill? You can:\n• Say 'this week' for the current week\n• Provide a specific date like '2025-10-07'\n• Say 'last week' for the previous week"
            
            else:
                response = f"I need more information for your weekly {selected_table} timesheet. What else can you tell me?"
        
        else:
            # All fields present - check for conflicts and validate
            conversation_state = 'weekly_checking_conflicts'
            
            # Validate hours
            if weekly_batch['hours'] > self.max_daily_hours:
                response = f"⚠️ {weekly_batch['hours']} hours exceeds the daily maximum of {self.max_daily_hours} hours. Please provide a valid number of hours per day."
                weekly_batch.pop('hours')
                
            # Validate project code
            elif not self.db.is_valid_project_code(selected_table, weekly_batch['project_code']):
                response = f"⚠️ Project code '{weekly_batch['project_code']}' is not valid for {selected_table} projects. Please use a valid project code or ask me to 'show my project codes'."
                weekly_batch.pop('project_code')
                
            else:
                # Check for existing timesheets
                existing_entries = self.db.check_existing_timesheets(user_id, selected_table, weekly_batch['dates'])
                weekly_batch['existing_entries'] = [asdict(entry) for entry in existing_entries]
                
                if existing_entries:
                    # Show conflicts
                    conversation_state = 'weekly_conflict_resolution'
                    existing_dates = [entry.date for entry in existing_entries]
                    conflict_list = "\n".join([f"• **{entry.date}**: {entry.hours}h on {entry.project_code} - {entry.task[:50]}..." 
                                             for entry in existing_entries])
                    
                    response = f"""⚠️ **Existing Timesheets Found**

I found existing timesheets for some dates in the week {weekly_batch['start_date']} to {weekly_batch['end_date']}:

{conflict_list}

**Options:**
1️⃣ Say **'override'** to replace all existing timesheets with new data
2️⃣ Say **'skip conflicts'** to only fill empty days  
3️⃣ Say **'cancel'** to start over

What would you like to do?"""
                    
                else:
                    # No conflicts - show draft
                    conversation_state = 'weekly_showing_draft'
                    response = self.show_weekly_draft(weekly_batch, selected_table)
        
        # Handle conflict resolution
        if conversation_state == 'weekly_conflict_resolution':
            if 'override' in user_input_lower:
                conversation_state = 'weekly_showing_draft'
                weekly_batch['override_existing'] = True
                response = self.show_weekly_draft(weekly_batch, selected_table)
                
            elif 'skip' in user_input_lower:
                conversation_state = 'weekly_showing_draft'
                weekly_batch['skip_existing'] = True
                
                # Filter out existing dates
                existing_dates = [entry['date'] for entry in weekly_batch.get('existing_entries', [])]
                new_dates = [date for date in weekly_batch['dates'] if date not in existing_dates]
                weekly_batch['dates'] = new_dates
                
                if not new_dates:
                    response = "All dates in this week already have timesheets. No new entries to create. Say 'new timesheet' to start fresh!"
                else:
                    response = self.show_weekly_draft(weekly_batch, selected_table)
                    
            elif 'cancel' in user_input_lower:
                conversation_state = 'greeting'
                weekly_batch = {}
                response = "Weekly timesheet cancelled. Say 'new timesheet' to start fresh!"
        
        # Handle draft confirmation
        elif conversation_state == 'weekly_showing_draft':
            if any(word in user_input_lower for word in ['yes', 'y', 'confirm', 'submit', 'ok', 'correct']):
                # Submit weekly timesheets
                success, record_ids = self.submit_weekly_timesheets(weekly_batch, user_id, selected_table)
                
                if success:
                    conversation_state = 'submitted'
                    table_emoji = "🚀" if selected_table == "Mars" else "🔮"
                    
                    total_hours = weekly_batch['hours'] * len(weekly_batch['dates'])
                    override_text = " (overriding existing entries)" if weekly_batch.get('override_existing') else ""
                    
                    response = f"""🎉 **Weekly Timesheet Submitted Successfully!**

{table_emoji} Your {selected_table} weekly timesheet has been saved{override_text}:

**Summary:**
• **Dates:** {weekly_batch['start_date']} to {weekly_batch['end_date']} 
• **Days Filed:** {len(weekly_batch['dates'])} days
• **Hours per day:** {weekly_batch['hours']}
• **Total Hours:** {total_hours}
• **System:** {weekly_batch['system']}
• **Project Code:** {weekly_batch['project_code']}
• **Record IDs:** {', '.join(map(str, record_ids))}

Say 'new timesheet' for another entry or 'history' to view recent timesheets! 😊"""
                    
                    # Reset for next entry
                    weekly_batch = {}
                    current_entry = {}
                    selected_table = ""
                    
                else:
                    response = "❌ Error saving weekly timesheet. Please try again or contact support."
                    
            elif any(word in user_input_lower for word in ['no', 'edit', 'change', 'wrong']):
                conversation_state = 'weekly_gathering'
                response = f"No problem! Let's fix your weekly {selected_table} timesheet. What would you like to change?"
                
            else:
                response = "Please say 'yes' to submit the weekly timesheet or 'no' to make changes."
        
        # Update session
        self.db.update_user_session(session_id, conversation_state, current_entry, selected_table, [], weekly_batch)
        
        history.append((user_input, response))
        return "", history

    def handle_single_timesheet_conversation(self, user_input: str, session_data: Dict, history: List[Tuple[str, str]], session_id: str) -> Tuple[str, List[Tuple[str, str]]]:
        """Handle regular single timesheet conversation"""
        
        conversation_state = session_data['conversation_state']
        current_entry = session_data['current_entry']
        selected_table = session_data['selected_table']
        conversation_history = session_data['conversation_history']
        user_id = session_data['user_id']
        
        user_input_clean = user_input.strip()
        user_input_lower = user_input_clean.lower()
        
        # Extract information from user input
        if not selected_table:
            table_pref = self.detect_table_preference(user_input)
            if table_pref:
                selected_table = table_pref
                current_entry['table_type'] = table_pref
        
        if not current_entry.get('hours'):
            hours = self.extract_hours_naturally(user_input)
            if hours:
                current_entry['hours'] = hours
        
        if not current_entry.get('system'):
            system = self.extract_system_info(user_input)
            if system:
                current_entry['system'] = system
        
        if not current_entry.get('project_code') and selected_table:
            project_code = self.detect_project_code(user_input, selected_table)
            if project_code:
                current_entry['project_code'] = project_code
        
        if not current_entry.get('task') and len(user_input_clean) > 10:
            # Only set task if it's a substantial description
            if not any(field in user_input_lower for field in ['mars', 'oracle', 'hours', 'hour']):
                current_entry['task'] = user_input_clean
        
        # Check for missing required fields
        missing_fields = [field for field in self.required_fields if not current_entry.get(field)]
        
        if missing_fields:
            # Ask for the first missing field
            field = missing_fields[0]
            
            if field == 'table_type':
                response = f"{random.choice(self.greetings)} I'm Tim, your timesheet assistant!\n\nAre you logging time for:\n🚀 **Mars projects** (space & exploration)\n🔮 **Oracle projects** (database & enterprise)\n\nJust say 'Mars' or 'Oracle'!\n\n💡 **Tip:** You can also say 'copy for the whole week' to fill Monday-Friday!"
            
            elif field == 'hours':
                response = f"How many hours did you work on {selected_table} projects today? (Maximum {self.max_daily_hours} hours per day)"
            
            elif field == 'system':
                response = f"What tools or systems did you use for your {selected_table} work? (e.g., Jira, GitHub, SQL Developer, etc.)"
            
            elif field == 'project_code':
                project_codes = self.db.get_project_codes(selected_table)
                if project_codes:
                    code_examples = ", ".join([pc.code for pc in project_codes[:3]])
                    response = f"Which {selected_table} project code were you working on? (e.g., {code_examples})\n\nIf you don't know the codes, just ask me to 'show my project codes'!"
                else:
                    response = f"Please provide the {selected_table} project code you were working on."
            
            elif field == 'task':
                response = f"Please describe what you actually worked on for project {current_entry.get('project_code', 'code')} today. Give me the details!"
            
            else:
                response = f"I need more information about your {selected_table} timesheet. What else can you tell me?"
            
        else:
            # All fields present - validate and submit
            
            # Validate hours
            if current_entry['hours'] > self.max_daily_hours:
                response = f"⚠️ {current_entry['hours']} hours exceeds the daily maximum of {self.max_daily_hours} hours. Please provide a valid number of hours."
                current_entry.pop('hours')  # Remove invalid hours
                
            # Validate project code
            elif not self.db.is_valid_project_code(selected_table, current_entry['project_code']):
                response = f"⚠️ Project code '{current_entry['project_code']}' is not valid for {selected_table} projects. Please use a valid project code or ask me to 'show my project codes'."
                current_entry.pop('project_code')  # Remove invalid code
                
            else:
                # All validation passed - submit timesheet
                entry = TimesheetEntry(
                    date=datetime.date.today().isoformat(),
                    hours=current_entry['hours'],
                    system=current_entry['system'],
                    project_code=current_entry['project_code'],
                    task=current_entry['task'],
                    submitted_at=datetime.datetime.now().isoformat(),
                    user_id=user_id,
                    table_type=selected_table
                )
                
                success, record_id = self.db.save_timesheet(entry)
                
                if success:
                    conversation_state = "submitted"
                    table_emoji = "🚀" if selected_table == "Mars" else "🔮"
                    
                    # Show warning for overtime
                    overtime_warning = ""
                    if current_entry['hours'] > 8:
                        overtime_warning = f"\n⚠️ Note: {current_entry['hours']} hours exceeds standard 8-hour workday"
                    
                    response = f"""🎉 **Timesheet Submitted Successfully!**

{table_emoji} Your {selected_table} timesheet has been saved:
• **Record ID:** {record_id}
• **Hours:** {current_entry['hours']}
• **System:** {current_entry['system']}
• **Project Code:** {current_entry['project_code']}
• **Task:** {current_entry['task'][:50]}{'...' if len(current_entry['task']) > 50 else ''}
• **Date:** {datetime.date.today().strftime('%Y-%m-%d')}{overtime_warning}

Say 'new timesheet' to log another entry, 'copy for the whole week' for weekly fill, or 'history' to view recent timesheets! 😊"""
                    
                    # Reset for next entry
                    current_entry = {}
                    selected_table = ""
                    
                else:
                    response = "❌ Error saving timesheet. Please try again or contact support."
        
        # Update session
        self.db.update_user_session(session_id, conversation_state, current_entry, selected_table, conversation_history)
        
        history.append((user_input, response))
        return "", history

    def show_weekly_draft(self, weekly_batch: Dict, selected_table: str) -> str:
        """Show weekly timesheet draft for confirmation"""
        table_emoji = "🚀" if selected_table == "Mars" else "🔮"
        
        dates_list = "\n".join([f"   • {date}" for date in weekly_batch['dates']])
        total_hours = weekly_batch['hours'] * len(weekly_batch['dates'])
        
        override_text = ""
        if weekly_batch.get('override_existing'):
            override_text = "\n⚠️ **This will override existing timesheets for conflicting dates**"
        elif weekly_batch.get('skip_existing'):
            override_text = "\n✅ **Only filling days without existing timesheets**"
        
        return f"""📋 **{selected_table} Weekly Timesheet Draft** {table_emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 **Week:** {weekly_batch['start_date']} to {weekly_batch['end_date']}
📆 **Dates to fill:**
{dates_list}
⏰ **Hours per day:** {weekly_batch['hours']}
📊 **Total hours:** {total_hours}
💻 **System:** {weekly_batch['system']}
📂 **Project Code:** {weekly_batch['project_code']}
📝 **Task:** {weekly_batch['task']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{override_text}

This will create {len(weekly_batch['dates'])} timesheet entries in the {selected_table}_timesheet table.

Does this look correct? Say **'yes'** to submit or **'no'** to make changes."""

    def submit_weekly_timesheets(self, weekly_batch: Dict, user_id: str, selected_table: str) -> Tuple[bool, List[int]]:
        """Submit weekly timesheet entries"""
        entries = []
        
        for date in weekly_batch['dates']:
            entry = TimesheetEntry(
                date=date,
                hours=weekly_batch['hours'],
                system=weekly_batch['system'],
                project_code=weekly_batch['project_code'],
                task=weekly_batch['task'],
                submitted_at=datetime.datetime.now().isoformat(),
                user_id=user_id,
                table_type=selected_table
            )
            entries.append(entry)
        
        # Determine if we need to update existing entries
        update_existing = weekly_batch.get('override_existing', False)
        
        return self.db.save_weekly_timesheets(entries, update_existing)

# Initialize the bot
db = DatabaseManager()
bot = ConversationalTimesheetBot(db)

# Global session storage
user_sessions = {}

def authenticate_user(username: str, password: str) -> Tuple[bool, str, str]:
    """Authenticate user and create session"""
    user = db.authenticate_user(username, password)
    if user:
        session_id = db.create_user_session(user.username)
        user_sessions[session_id] = {"username": user.username, "role": user.role}
        return True, session_id, user.role
    return False, "", ""

def create_gradio_app():
    """Create the enhanced Gradio application with weekly features"""
    
    custom_css = """
    .gradio-container {
        max-width: 1200px !important;
        margin: 0 auto !important;
    }
    
    .chat-message {
        padding: 12px !important;
        margin: 8px 0 !important;
        border-radius: 12px !important;
    }
    
    .message.user {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        margin-left: 20% !important;
    }
    
    .message.bot {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%) !important;
        color: white !important;
        margin-right: 20% !important;
    }
    
    .auth-container {
        max-width: 400px;
        margin: 50px auto;
        padding: 30px;
        border-radius: 15px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    
    .feature-highlight {
        background: #e3f2fd;
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
        border-left: 4px solid #2196f3;
    }
    
    .weekly-feature {
        background: #f3e5f5;
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
        border-left: 4px solid #9c27b0;
    }
    """
    
    with gr.Blocks(css=custom_css, title="Enhanced Weekly Timesheet Assistant", theme=gr.themes.Soft()) as demo:
        
        # Authentication state
        session_state = gr.State("")
        user_role_state = gr.State("")
        authenticated_state = gr.State(False)
        
        with gr.Column(visible=True) as auth_container:
            gr.Markdown("""
            # 🔐 Enhanced Conversational Timesheet Assistant
            
            **🆕 NEW: Weekly Timesheet Feature!**
            
            **Demo Accounts:**
            - **Admin:** username: `admin`, password: `admin123`
            - **User:** username: `user1`, password: `user123`
            
            **🌟 Key Features:**
            ✅ **Weekly Copy:** Fill Monday-Friday with same timesheet  
            ✅ **Conflict Detection:** Warns about existing entries  
            ✅ **Override Option:** Replace or skip existing timesheets  
            ✅ **Project Code Validation:** Only predefined codes accepted  
            ✅ **Natural Conversation:** Smart extraction and prompting  
            ✅ **Multi-user Sessions:** Persistent state per user  
            ✅ **Complete Audit Trail:** Full logging and history
            """, elem_classes=["auth-container"])
            
            with gr.Row():
                username_input = gr.Textbox(label="Username", placeholder="Enter username")
                password_input = gr.Textbox(label="Password", type="password", placeholder="Enter password")
            
            login_btn = gr.Button("🔑 Login", variant="primary", size="lg")
            auth_message = gr.Markdown("")
        
        with gr.Column(visible=False) as main_container:
            
            # Header with user info
            with gr.Row():
                user_info = gr.Markdown("")
                logout_btn = gr.Button("🚪 Logout", size="sm")
            
            # Main tabs
            with gr.Tabs() as main_tabs:
                
                # Chat Tab
                with gr.Tab("💬 Chat Assistant", id="chat"):
                    gr.Markdown("""
                    ## 🤖 Tim - Enhanced Weekly Timesheet Assistant
                    
                    **🆕 NEW: Weekly Timesheet Functionality!**
                    """)
                    
                    # Weekly feature highlight
                    gr.Markdown("""
                    ### 📅 Weekly Timesheet Commands:
                    - **"copy for the whole week"** - Fill Monday-Friday with same data
                    - **"weekly timesheet for 2025-10-07"** - Fill specific week
                    - **"same timesheet for this week"** - Current week batch fill
                    
                    ### 📋 Other Commands:
                    - **"show my project codes"** - List available codes
                    - **"new timesheet"** - Start fresh single entry
                    - **"reset"** - Clear conversation
                    """, elem_classes=["weekly-feature"])
                    
                    # Project codes reference
                    gr.Markdown("""
                    ### 🎯 Quick Reference - Project Codes:
                    **Mars Projects:** MARS001 (Navigation), MARS002 (Life Support), MARS003 (Communication), MARS004 (Exploration), MARS005 (Sample Collection)  
                    **Oracle Projects:** ORA100 (Performance), ORA101 (Migration), ORA102 (ETL), ORA103 (Security), ORA104 (Backup)
                    """, elem_classes=["feature-highlight"])
                    
                    chatbot = gr.Chatbot(
                        [],
                        elem_id="chatbot",
                        bubble_full_width=False,
                        height=650,
                        show_label=False,
                        avatar_images=("👤", "🤖")
                    )
                    
                    with gr.Row():
                        msg = gr.Textbox(
                            placeholder="Try: 'Mars, copy for the whole week, 8 hours, MARS001' or 'show my project codes'",
                            show_label=False,
                            scale=4
                        )
                        send_btn = gr.Button("Send 💬", scale=1, variant="primary")
                    
                    with gr.Row():
                        clear_btn = gr.Button("🔄 Reset Chat", scale=1)
                        gr.Markdown("**🆕 Enhanced:** Weekly timesheet copying with conflict detection!", scale=3)
                
                # History Tab
                with gr.Tab("📊 Timesheet History", id="history"):
                    gr.Markdown("## 📊 Your Timesheet History with Weekly View")
                    
                    with gr.Row():
                        table_filter = gr.Radio(["Mars", "Oracle"], label="Table", value="Mars")
                        start_date_filter = gr.Textbox(label="Start Date (YYYY-MM-DD)", placeholder="2025-01-01")
                        end_date_filter = gr.Textbox(label="End Date (YYYY-MM-DD)", placeholder="2025-12-31")
                    
                    with gr.Row():
                        page_input = gr.Number(label="Page", value=1, minimum=1)
                        per_page_input = gr.Number(label="Per Page", value=10, minimum=5, maximum=50)
                        load_history_btn = gr.Button("🔍 Load History", variant="primary")
                    
                    history_display = gr.Dataframe(
                        headers=["ID", "Date", "Hours", "System", "Project Code", "Task", "Status", "Created"],
                        datatype=["number", "str", "number", "str", "str", "str", "str", "str"],
                        col_count=(8, "fixed"),
                        interactive=False
                    )
                    
                    pagination_info = gr.Markdown("")
                
                # Project Codes Tab
                with gr.Tab("📋 Project Codes", id="projects"):
                    gr.Markdown("## 📋 Available Project Codes")
                    
                    with gr.Tabs():
                        with gr.Tab("🚀 Mars Projects"):
                            mars_codes = db.get_project_codes("Mars")
                            mars_data = [[pc.code, pc.description, "Active" if pc.is_active else "Inactive"] for pc in mars_codes]
                            
                            gr.Dataframe(
                                value=mars_data,
                                headers=["Project Code", "Description", "Status"],
                                datatype=["str", "str", "str"],
                                col_count=(3, "fixed"),
                                interactive=False
                            )
                        
                        with gr.Tab("🔮 Oracle Projects"):
                            oracle_codes = db.get_project_codes("Oracle")
                            oracle_data = [[pc.code, pc.description, "Active" if pc.is_active else "Inactive"] for pc in oracle_codes]
                            
                            gr.Dataframe(
                                value=oracle_data,
                                headers=["Project Code", "Description", "Status"],
                                datatype=["str", "str", "str"],
                                col_count=(3, "fixed"),
                                interactive=False
                            )
        
        # Event handlers
        def handle_login(username, password):
            success, session_id, role = authenticate_user(username, password)
            if success:
                return (
                    gr.update(visible=False),  # Hide auth container
                    gr.update(visible=True),   # Show main container
                    session_id,                # Store session
                    role,                      # Store role
                    True,                      # Set authenticated
                    f"✅ Welcome **{username}** ({role}) - Weekly timesheet features enabled! 📅",  # User info
                    "",                        # Clear auth message
                )
            else:
                return (
                    gr.update(visible=True),   # Keep auth container visible
                    gr.update(visible=False),  # Keep main container hidden
                    "",                        # No session
                    "",                        # No role
                    False,                     # Not authenticated
                    "",                        # No user info
                    "❌ Invalid credentials. Please try again.",  # Auth error message
                )
        
        def handle_logout():
            return (
                gr.update(visible=True),   # Show auth container
                gr.update(visible=False),  # Hide main container
                "",                        # Clear session
                "",                        # Clear role
                False,                     # Not authenticated
                "",                        # Clear user info
                "",                        # Clear auth message
                [],                        # Clear chat history
            )
        
        def handle_chat(message, history, session_id):
            if not session_id or session_id not in user_sessions:
                return "", history + [("", "❌ Session expired. Please log in again.")]
            
            return bot.process_conversation(message, session_id, history)
        
        def handle_load_history(table_type, start_date, end_date, page, per_page, session_id):
            if not session_id or session_id not in user_sessions:
                return [], "❌ Session expired"
            
            user_id = user_sessions[session_id]["username"]
            data = db.load_timesheets_paginated(
                user_id, table_type, int(page), int(per_page), start_date, end_date
            )
            
            # Format data for display
            display_data = []
            for ts in data['timesheets']:
                display_data.append([
                    ts.id, ts.date, ts.hours, ts.system, ts.project_code,
                    ts.task[:100] + "..." if len(ts.task) > 100 else ts.task,
                    ts.validation_status, ts.created_at[:19] if ts.created_at else ""
                ])
            
            pagination = f"Page {data['page']} of {data['total_pages']} | Total entries: {data['total_count']}"
            
            return display_data, pagination
        
        # Wire up events
        login_btn.click(
            handle_login,
            inputs=[username_input, password_input],
            outputs=[auth_container, main_container, session_state, user_role_state, 
                    authenticated_state, user_info, auth_message]
        )
        
        logout_btn.click(
            handle_logout,
            outputs=[auth_container, main_container, session_state, user_role_state,
                    authenticated_state, user_info, auth_message, chatbot]
        )
        
        msg.submit(handle_chat, [msg, chatbot, session_state], [msg, chatbot])
        send_btn.click(handle_chat, [msg, chatbot, session_state], [msg, chatbot])
        
        clear_btn.click(lambda: [], outputs=[chatbot])
        
        load_history_btn.click(
            handle_load_history,
            inputs=[table_filter, start_date_filter, end_date_filter, page_input, per_page_input, session_state],
            outputs=[history_display, pagination_info]
        )
        
        # Enhanced welcome message
        demo.load(
            lambda: [("", """🤖 Hey there! I'm Tim, your enhanced conversational timesheet assistant! 

**🆕 NEW WEEKLY FEATURES:**
📅 Say **"copy for the whole week"** to fill Monday-Friday with the same timesheet
📅 Mention any date like **"2025-10-07"** to fill that entire week
📅 I'll check for conflicts and ask if you want to override existing entries

**📋 PROJECT CODES:**  
🚀 **Mars:** MARS001-MARS005 (Navigation, Life Support, Communication, Exploration, Sample Collection)  
🔮 **Oracle:** ORA100-ORA104 (Performance, Migration, ETL, Security, Backup)

**💬 Getting Started:**
1️⃣ Tell me **Mars** or **Oracle** for your project type  
2️⃣ Say **"show my project codes"** if you need the full list  
3️⃣ For single entry: just tell me hours, system, code, and task  
4️⃣ For weekly: say **"copy for the whole week"** or **"weekly timesheet"**

Let's make timesheets smart and conversational! 😊""")],
            outputs=[chatbot]
        )
    
    return demo

def main():
    """Main function to run the enhanced app"""
    print("🚀 Starting Enhanced Weekly Timesheet Assistant...")
    print("✅ NEW FEATURES:")
    print("   📅 Weekly timesheet copying (Monday-Friday)")
    print("   🔍 Conflict detection for existing entries")  
    print("   ⚡ Override and skip functionality")
    print("   🛡️ Enhanced project code validation")
    print("   💬 Advanced conversational flow")
    print()
    print("🔐 Demo accounts:")
    print("   • Admin: admin / admin123")  
    print("   • User: user1 / user123")
    print()
    print("💡 Try saying:")
    print("   • 'Mars, copy for the whole week, 8 hours, MARS001'")
    print("   • 'weekly timesheet for 2025-10-07'")
    print("   • 'show my project codes'")
    
    app = create_gradio_app()
    
    app.launch(
        share=False,
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        show_api=False
    )

if __name__ == "__main__":
    main()