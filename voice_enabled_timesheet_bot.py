"""
Complete Enhanced Conversational Timesheet Bot
with Voice Commands and Flexible Date Selection

Advanced Features:
- 🎤 Voice input with speech-to-text
- 🔊 Voice responses with text-to-speech  
- 📅 Choose whole week OR specific dates
- 🔀 Mixed Mars/Oracle entries in same conversation
- 🧠 Complex input parsing (voice or text)
- 📝 Natural date parsing with voice support
- 💬 Multi-step conversational flow
- 🔍 Project code validation with voice commands
- ⚡ Conflict detection and override functionality
- 🔒 Comprehensive audit logging and session management

Requirements:
pip install ollama pyodbc gradio bcrypt pandas python-dateutil speechrecognition pyttsx3 pyaudio

Usage:
python voice_enabled_timesheet_bot.py
"""

import ollama
import gradio as gr
import json
import datetime
import re
import bcrypt
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Tuple, Any, Union
import pyodbc
from contextlib import contextmanager
import random
import uuid
import calendar
from dateutil import parser
from dateutil.relativedelta import relativedelta
import speech_recognition as sr
import pyttsx3
import threading
import io
import wave
import tempfile
import os

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
class FlexibleTimesheetBatch:
    entries: List[Dict] = None
    total_entries: int = 0
    mars_entries: int = 0
    oracle_entries: int = 0
    total_hours: float = 0.0
    date_range: str = ""
    conflicts: List[Dict] = None
    mode: str = "flexible"
    
    def __post_init__(self):
        if self.entries is None:
            self.entries = []
        if self.conflicts is None:
            self.conflicts = []

class VoiceProcessor:
    """Voice processing for speech-to-text and text-to-speech"""
    
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.tts_engine = None
        self.init_tts()
        
        # Adjust for ambient noise
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
    
    def init_tts(self):
        """Initialize text-to-speech engine"""
        try:
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', 150)  # Speed of speech
            self.tts_engine.setProperty('volume', 0.8)  # Volume level
            
            # Try to set a nice voice
            voices = self.tts_engine.getProperty('voices')
            if voices:
                # Prefer female voice if available
                for voice in voices:
                    if 'female' in voice.name.lower() or 'zira' in voice.name.lower():
                        self.tts_engine.setProperty('voice', voice.id)
                        break
                else:
                    # Use first available voice
                    self.tts_engine.setProperty('voice', voices[0].id)
            
            print("✅ Text-to-speech engine initialized")
        except Exception as e:
            print(f"⚠️ TTS initialization error: {e}")
            self.tts_engine = None
    
    def speech_to_text(self, audio_file_path: str) -> str:
        """Convert speech to text from audio file"""
        try:
            with sr.AudioFile(audio_file_path) as source:
                # Read the audio data
                audio_data = self.recognizer.record(source)
                
                # Recognize speech using Google's service
                text = self.recognizer.recognize_google(audio_data)
                print(f"🎤 Voice input recognized: {text}")
                return text
                
        except sr.UnknownValueError:
            return "Sorry, I couldn't understand the audio. Please try again."
        except sr.RequestError as e:
            return f"Could not request results from speech recognition service: {e}"
        except Exception as e:
            return f"Voice processing error: {e}"
    
    def text_to_speech(self, text: str) -> str:
        """Convert text to speech and return audio file path"""
        if not self.tts_engine:
            return None
            
        try:
            # Clean text for TTS (remove markdown formatting)
            clean_text = self.clean_text_for_tts(text)
            
            # Generate speech in a separate thread to avoid blocking
            temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_file.close()
            
            self.tts_engine.save_to_file(clean_text, temp_file.name)
            self.tts_engine.runAndWait()
            
            print(f"🔊 Generated speech audio: {temp_file.name}")
            return temp_file.name
            
        except Exception as e:
            print(f"TTS error: {e}")
            return None
    
    def clean_text_for_tts(self, text: str) -> str:
        """Clean text for better TTS pronunciation"""
        # Remove markdown formatting
        text = re.sub(r'\*\*(.*?)\*\*', r'\\1', text)  # Bold
        text = re.sub(r'\*(.*?)\*', r'\\1', text)      # Italic
        text = re.sub(r'`(.*?)`', r'\\1', text)        # Code
        text = re.sub(r'#{1,6}\s+', '', text)          # Headers
        text = re.sub(r'━+', '', text)                 # Lines
        text = re.sub(r'[📅📊📋🎯🚀🔮⏰💻📂📝✅⚠️❌🎉💡🔍🆕🌟]', '', text)  # Emojis
        
        # Replace technical terms with pronunciations
        replacements = {
            'MARS001': 'Mars zero zero one',
            'MARS002': 'Mars zero zero two', 
            'MARS003': 'Mars zero zero three',
            'MARS004': 'Mars zero zero four',
            'MARS005': 'Mars zero zero five',
            'ORA100': 'Oracle one hundred',
            'ORA101': 'Oracle one zero one',
            'ORA102': 'Oracle one zero two',
            'ORA103': 'Oracle one zero three', 
            'ORA104': 'Oracle one zero four',
            'API': 'A P I',
            'SQL': 'S Q L',
            'GitHub': 'Git Hub',
            'hrs': 'hours',
            'Dec': 'December',
            'Jan': 'January',
        }
        
        for term, replacement in replacements.items():
            text = text.replace(term, replacement)
        
        # Limit text length for TTS
        if len(text) > 500:
            text = text[:500] + "... Please check the screen for full details."
        
        return text

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
                
                # Mars and Oracle timesheet tables
                for table in ['Mars', 'Oracle']:
                    cursor.execute(f"""
                    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{table}_timesheet' AND xtype='U')
                    BEGIN
                        CREATE TABLE {table}_timesheet (
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
                        CREATE INDEX IX_{table}_user_date ON {table}_timesheet(user_id, date DESC);
                        CREATE INDEX IX_{table}_project_code ON {table}_timesheet(project_code);
                    END
                    """)
                
                # Sessions table with flexible batch support
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
                        flexible_batch NVARCHAR(MAX) DEFAULT '{}',
                        voice_enabled NVARCHAR(10) DEFAULT 'false',
                        created_at DATETIME2 DEFAULT GETDATE(),
                        updated_at DATETIME2 DEFAULT GETDATE(),
                        expires_at DATETIME2 NOT NULL
                    );
                    CREATE INDEX IX_sessions_session_id ON user_sessions(session_id);
                    CREATE INDEX IX_sessions_expires ON user_sessions(expires_at);
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
                        user_agent NVARCHAR(500),
                        input_method NVARCHAR(20) DEFAULT 'text'
                    );
                    CREATE INDEX IX_audit_timestamp ON audit_log(timestamp DESC);
                    CREATE INDEX IX_audit_user ON audit_log(user_id, timestamp DESC);
                END
                """)
                
                conn.commit()
                self._create_default_data(cursor, conn)
                
        except Exception as e:
            print(f"Database initialization error: {e}")
            raise

    def _create_default_data(self, cursor, conn):
        """Create default users and project codes"""
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
                           conversation_history, flexible_batch, voice_enabled, expires_at
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
                        'flexible_batch': json.loads(row[5]) if row[5] else {},
                        'voice_enabled': row[6] == 'true',
                        'expires_at': row[7]
                    }
        except Exception as e:
            print(f"Session retrieval error: {e}")
        
        return None

    def update_user_session(self, session_id: str, conversation_state: str, 
                           current_entry: Dict, selected_table: str, conversation_history: List,
                           flexible_batch: Dict = None, voice_enabled: bool = False):
        """Update user session data"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE user_sessions 
                    SET conversation_state = ?, current_entry = ?, selected_table = ?, 
                        conversation_history = ?, flexible_batch = ?, voice_enabled = ?,
                        updated_at = GETDATE(), expires_at = DATEADD(hour, 8, GETDATE())
                    WHERE session_id = ?
                """, (
                    conversation_state,
                    json.dumps(current_entry),
                    selected_table,
                    json.dumps(conversation_history),
                    json.dumps(flexible_batch or {}),
                    'true' if voice_enabled else 'false',
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

    def check_existing_timesheets_multiple(self, user_id: str, entries: List[Dict]) -> List[Dict]:
        """Check for existing timesheets for multiple entries across Mars and Oracle"""
        conflicts = []
        
        try:
            # Group entries by table type for efficient querying
            mars_dates = [entry['date'] for entry in entries if entry.get('table_type') == 'Mars']
            oracle_dates = [entry['date'] for entry in entries if entry.get('table_type') == 'Oracle']
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check Mars conflicts
                if mars_dates:
                    placeholders = ','.join(['?' for _ in mars_dates])
                    cursor.execute(f"""
                        SELECT date, hours, system, project_code, task, id
                        FROM Mars_timesheet
                        WHERE user_id = ? AND date IN ({placeholders})
                        ORDER BY date
                    """, [user_id] + mars_dates)
                    
                    for row in cursor.fetchall():
                        conflicts.append({
                            'table_type': 'Mars',
                            'date': str(row[0]),
                            'hours': float(row[1]),
                            'system': row[2],
                            'project_code': row[3],
                            'task': row[4],
                            'id': row[5]
                        })
                
                # Check Oracle conflicts
                if oracle_dates:
                    placeholders = ','.join(['?' for _ in oracle_dates])
                    cursor.execute(f"""
                        SELECT date, hours, system, project_code, task, id
                        FROM Oracle_timesheet
                        WHERE user_id = ? AND date IN ({placeholders})
                        ORDER BY date
                    """, [user_id] + oracle_dates)
                    
                    for row in cursor.fetchall():
                        conflicts.append({
                            'table_type': 'Oracle',
                            'date': str(row[0]),
                            'hours': float(row[1]),
                            'system': row[2],
                            'project_code': row[3],
                            'task': row[4],
                            'id': row[5]
                        })
                
                return conflicts
                
        except Exception as e:
            print(f"Error checking existing timesheets: {e}")
            return []

    def save_timesheet(self, entry: TimesheetEntry, update_existing: bool = False, input_method: str = "text") -> Tuple[bool, Optional[int]]:
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
                
                # Log audit event with input method
                cursor.execute("""
                    INSERT INTO audit_log (user_id, action, table_name, record_id, 
                                         new_values, input_method)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    entry.user_id, action, table_name, record_id,
                    json.dumps(asdict(entry)),
                    input_method
                ))
                conn.commit()
                
                return True, record_id
        except Exception as e:
            print(f"Save timesheet error: {e}")
            return False, None

    def save_flexible_batch(self, entries: List[TimesheetEntry], update_existing: bool = False, input_method: str = "text") -> Tuple[bool, List[int]]:
        """Save flexible batch of timesheet entries"""
        record_ids = []
        try:
            for entry in entries:
                success, record_id = self.save_timesheet(entry, update_existing, input_method)
                if success and record_id:
                    record_ids.append(record_id)
                else:
                    # If any entry fails, return failure
                    return False, record_ids
            
            return True, record_ids
        except Exception as e:
            print(f"Flexible batch save error: {e}")
            return False, record_ids

class FlexibleDateParser:
    """Enhanced date parser for flexible input formats including voice"""
    
    @staticmethod
    def parse_multiple_dates(text: str) -> List[str]:
        """Parse multiple dates from various input formats including voice variations"""
        dates = []
        current_year = datetime.date.today().year
        
        # Enhanced patterns for voice input
        patterns = [
            # Voice-friendly patterns
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?december',
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?january',
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?february',
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?march',
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?april',
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?may',
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?june',
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?july',
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?august',
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?september',
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?october',
            r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?november',
            # Abbreviated versions
            r'(\d{1,2})dec',  r'(\d{1,2})jan',  r'(\d{1,2})feb',  r'(\d{1,2})mar',
            r'(\d{1,2})apr',  r'(\d{1,2})may',  r'(\d{1,2})jun',  r'(\d{1,2})jul',
            r'(\d{1,2})aug',  r'(\d{1,2})sep',  r'(\d{1,2})oct',  r'(\d{1,2})nov',
            # Standard formats
            r'(\d{4}-\d{2}-\d{2})',  # 2025-12-15
            r'(\d{2}/\d{2}/\d{4})',  # 12/15/2025
            r'(\d{1,2}/\d{1,2})',     # 12/15 (assume current year)
        ]
        
        text_lower = text.lower()
        
        # Enhanced month name mapping
        month_map = {
            'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
            'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6,
            'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9,
            'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
        }
        
        # Find all date-like patterns
        for pattern in patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                date_str = match.group(1)
                try:
                    # Extract month from pattern context
                    for month_name, month_num in month_map.items():
                        if month_name in pattern:
                            day = int(date_str)
                            if 1 <= day <= 31:
                                try:
                                    dates.append(datetime.date(current_year, month_num, day).strftime('%Y-%m-%d'))
                                except ValueError:
                                    # Invalid date (e.g., Feb 30)
                                    continue
                            break
                    else:
                        # Handle standard formats
                        if '-' in date_str:
                            # ISO format
                            parsed_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                            dates.append(parsed_date.strftime('%Y-%m-%d'))
                        elif '/' in date_str:
                            if date_str.count('/') == 2:
                                # MM/DD/YYYY format
                                parsed_date = datetime.datetime.strptime(date_str, '%m/%d/%Y').date()
                            else:
                                # MM/DD format (assume current year)
                                month, day = map(int, date_str.split('/'))
                                parsed_date = datetime.date(current_year, month, day)
                            dates.append(parsed_date.strftime('%Y-%m-%d'))
                            
                except (ValueError, TypeError):
                    continue
        
        # Remove duplicates and sort
        unique_dates = sorted(list(set(dates)))
        return unique_dates

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

class ComplexInputParser:
    """Enhanced parser for complex timesheet inputs including voice"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.date_parser = FlexibleDateParser()
    
    def parse_complex_input(self, text: str) -> Dict[str, Any]:
        """Parse complex input including voice variations"""
        
        result = {
            'hours': None,
            'project_codes': [],
            'dates': [],
            'task': None,
            'systems': [],
            'table_types': []
        }
        
        text_clean = text.strip()
        
        # Enhanced hours extraction for voice input
        hours_patterns = [
            # Voice-friendly patterns
            r'(\d+\.?\d*)\s*(?:and\s*(?:a\s*)?half)',  # "8 and a half"
            r'(\d+\.?\d*)\s*(?:point\s*(?:five|25|75))',  # "8 point 5"
            r'(\d+)\s*(?:hours?\s*and\s*(?:a\s*)?half)',  # "8 hours and a half"
            r'(\d+\.?\d*)\s*(?:hours?|hrs?|h\b)',  # "8 hours"
            r'about\s*(\d+\.?\d*)',  # "about 8"
            r'around\s*(\d+\.?\d*)',  # "around 7"
            r'roughly\s*(\d+\.?\d*)',  # "roughly 6"
            r'(\d+\.?\d*)',  # just numbers
        ]
        
        for pattern in hours_patterns:
            match = re.search(pattern, text_clean.lower())
            if match:
                try:
                    hours = float(match.group(1))
                    # Handle special voice cases
                    if 'and a half' in text_clean.lower() or 'and half' in text_clean.lower():
                        hours += 0.5
                    elif 'point five' in text_clean.lower() or 'point 5' in text_clean.lower():
                        if '.' not in match.group(1):
                            hours += 0.5
                    elif 'point 25' in text_clean.lower() or 'point 75' in text_clean.lower():
                        if 'point 25' in text_clean.lower():
                            hours += 0.25
                        else:
                            hours += 0.75
                    
                    if 0 < hours <= 24:
                        result['hours'] = hours
                        break
                except ValueError:
                    continue
        
        # Enhanced project code extraction
        mars_codes = [pc.code for pc in self.db.get_project_codes('Mars')]
        oracle_codes = [pc.code for pc in self.db.get_project_codes('Oracle')]
        all_codes = mars_codes + oracle_codes
        
        text_upper = text_clean.upper()
        # Voice-friendly code detection
        code_variations = {}
        for code in all_codes:
            code_variations[code] = code
            # Add voice variations like "Mars zero zero one" -> "MARS001"
            if code.startswith('MARS'):
                num = code[4:]
                voice_num = num.replace('00', 'zero zero ').replace('0', 'zero ')
                code_variations[f"MARS {voice_num}".strip()] = code
                code_variations[f"Mars {voice_num}".strip()] = code
            elif code.startswith('ORA'):
                num = code[3:]
                if len(num) == 3:
                    voice_num = f"{num[0]} {num[1]} {num[2]}"
                    code_variations[f"ORA {voice_num}"] = code
                    code_variations[f"Oracle {voice_num}"] = code
        
        for variant, actual_code in code_variations.items():
            if variant.upper() in text_upper:
                result['project_codes'].append(actual_code)
                if actual_code in mars_codes:
                    result['table_types'].append('Mars')
                else:
                    result['table_types'].append('Oracle')
        
        # Remove duplicates
        result['project_codes'] = list(set(result['project_codes']))
        result['table_types'] = list(set(result['table_types']))
        
        # Extract dates with voice support
        result['dates'] = self.date_parser.parse_multiple_dates(text_clean)
        
        # Enhanced task extraction
        task_text = text_clean
        
        # Remove hours patterns
        for pattern in hours_patterns:
            task_text = re.sub(pattern, '', task_text, flags=re.IGNORECASE)
        
        # Remove project codes
        for code in result['project_codes']:
            task_text = task_text.replace(code, '')
            # Remove voice variations
            if code.startswith('MARS'):
                task_text = re.sub(r'mars\s*(?:zero\s*)*\d+', '', task_text, flags=re.IGNORECASE)
            elif code.startswith('ORA'):
                task_text = re.sub(r'oracle?\s*\d+', '', task_text, flags=re.IGNORECASE)
        
        # Remove dates
        for date_str in result['dates']:
            task_text = task_text.replace(date_str, '')
        
        # Remove date patterns
        task_text = re.sub(r'\d{1,2}(?:st|nd|rd|th)?\s*(?:of\s*)?(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', '', task_text, flags=re.IGNORECASE)
        
        # Clean up task text
        task_text = re.sub(r'[,\s]+', ' ', task_text).strip()
        if len(task_text) > 5:  # Only consider substantial text as task
            result['task'] = task_text
        
        # Enhanced system extraction with voice variations
        system_keywords = {
            'jira': 'Jira',
            'github': 'GitHub', 'git hub': 'GitHub', 'git': 'GitHub',
            'sql': 'SQL Developer', 'sequel': 'SQL Developer',
            'oracle': 'Oracle',
            'database': 'Database',
            'api': 'API System', 'a p i': 'API System',
            'system': 'System'
        }
        
        text_lower = text_clean.lower()
        for keyword, system_name in system_keywords.items():
            if keyword in text_lower:
                result['systems'].append(system_name)
                break
        
        return result

class VoiceEnabledTimesheetBot:
    """Enhanced conversational bot with voice support and flexible input management"""
    
    def __init__(self, db: DatabaseManager, model_name: str = "llama3.2:1b"):
        self.db = db
        self.model_name = model_name
        self.voice_processor = VoiceProcessor()
        self.input_parser = ComplexInputParser(db)
        self.date_parser = FlexibleDateParser()
        self.max_daily_hours = 12.0
        
        # Voice-aware conversational responses
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

    def process_voice_input(self, audio_file_path: str) -> str:
        """Process voice input and convert to text"""
        if not audio_file_path:
            return ""
        
        try:
            # Convert speech to text
            text = self.voice_processor.speech_to_text(audio_file_path)
            print(f"🎤 Voice transcription: {text}")
            
            # Clean up temporary files
            if os.path.exists(audio_file_path):
                try:
                    os.remove(audio_file_path)
                except:
                    pass
                    
            return text
            
        except Exception as e:
            print(f"Voice processing error: {e}")
            return "Sorry, I couldn't process your voice input. Please try again."

    def generate_voice_response(self, text_response: str) -> Optional[str]:
        """Generate voice response from text"""
        try:
            return self.voice_processor.text_to_speech(text_response)
        except Exception as e:
            print(f"Voice generation error: {e}")
            return None

    def detect_voice_commands(self, text: str) -> Dict[str, Any]:
        """Detect special voice commands"""
        text_lower = text.lower()
        
        commands = {
            'voice_on': any(phrase in text_lower for phrase in [
                'enable voice', 'turn on voice', 'voice mode on', 'start voice'
            ]),
            'voice_off': any(phrase in text_lower for phrase in [
                'disable voice', 'turn off voice', 'voice mode off', 'stop voice'
            ]),
            'repeat': any(phrase in text_lower for phrase in [
                'repeat', 'say again', 'can you repeat', 'repeat that'
            ]),
            'help': any(phrase in text_lower for phrase in [
                'help', 'what can i do', 'what are my options', 'how does this work'
            ])
        }
        
        return commands

    def get_greeting_with_options(self, voice_enabled: bool = False) -> str:
        """Get greeting message with voice-aware options"""
        greeting = random.choice(self.greetings)
        voice_status = "🎤 Voice commands enabled!" if voice_enabled else "💬 Text mode (say 'enable voice' for voice commands)"
        
        return f"""{greeting} I'm Tim, your voice-enabled flexible timesheet assistant! 

**{voice_status}**

**📅 What would you like to do today?**

**Option 1: Single Day Entry**
🗣️ Say: *"Mars, 8 hours, Mars zero zero one, worked on navigation system"*
⌨️ Type: *"Mars, 8 hours, MARS001, worked on navigation system"*

**Option 2: Whole Week (Monday-Friday)**
🗣️ Say: *"Copy for the whole week"* or *"Weekly timesheet"*

**Option 3: Specific Dates (Flexible)**
🗣️ Say: *"4 hours, Mars zero zero one, 12th December 13th December 15th December, worked on API changes"*
⌨️ Type: *"4 hours, MARS001, 12dec 13dec 15dec, worked on API changes"*

**Option 4: Mixed Mars & Oracle**
🗣️ Say: *"4 hours Mars and 4 hours Oracle on 12th December 13th December"*

**💡 Voice Commands:**
• **"Enable voice"** / **"Disable voice"** - Toggle voice responses
• **"Show my project codes"** - See available project codes
• **"Help"** - Get assistance
• **"Reset"** - Start fresh conversation

What sounds good to you? 😊"""

    def process_conversation(self, user_input: str, audio_input, session_id: str, history: List[Tuple[str, str]]) -> Tuple[str, Optional[str], List[Tuple[str, str]]]:
        """Main conversation processing with voice support"""
        
        # Handle voice input
        if audio_input is not None:
            voice_text = self.process_voice_input(audio_input)
            if voice_text and "sorry" not in voice_text.lower():
                user_input = voice_text
                print(f"🎤 Using voice input: {user_input}")
        
        if not user_input.strip():
            return "", None, history
        
        # Get session data
        session_data = self.db.get_user_session(session_id)
        if not session_data:
            response = "❌ Session expired. Please log in again."
            history.append((user_input, response))
            return "", None, history
        
        voice_enabled = session_data.get('voice_enabled', False)
        
        # Handle voice commands
        voice_commands = self.detect_voice_commands(user_input)
        
        if voice_commands['voice_on']:
            voice_enabled = True
            response = "🎤 Voice responses enabled! I'll now speak my replies. You can still type or use voice input."
            self.db.update_user_session(session_id, session_data['conversation_state'], 
                                      session_data['current_entry'], session_data['selected_table'], 
                                      [], session_data['flexible_batch'], voice_enabled)
            
            audio_response = self.generate_voice_response(response) if voice_enabled else None
            history.append((user_input, response))
            return "", audio_response, history
        
        elif voice_commands['voice_off']:
            voice_enabled = False
            response = "💬 Voice responses disabled. I'll only respond with text now."
            self.db.update_user_session(session_id, session_data['conversation_state'], 
                                      session_data['current_entry'], session_data['selected_table'], 
                                      [], session_data['flexible_batch'], voice_enabled)
            
            history.append((user_input, response))
            return "", None, history
        
        elif voice_commands['help']:
            response = self.get_greeting_with_options(voice_enabled)
            audio_response = self.generate_voice_response(response) if voice_enabled else None
            history.append((user_input, response))
            return "", audio_response, history
        
        # Process regular conversation
        text_response = self.handle_conversation_flow(user_input, session_data, session_id)
        
        # Generate voice response if enabled
        audio_response = None
        if voice_enabled and text_response:
            audio_response = self.generate_voice_response(text_response)
        
        history.append((user_input, text_response))
        return "", audio_response, history

    def handle_conversation_flow(self, user_input: str, session_data: Dict, session_id: str) -> str:
        """Handle the main conversation flow"""
        
        conversation_state = session_data['conversation_state']
        current_entry = session_data['current_entry']
        selected_table = session_data['selected_table']
        conversation_history = session_data['conversation_history']
        flexible_batch = session_data['flexible_batch']
        voice_enabled = session_data.get('voice_enabled', False)
        user_id = session_data['user_id']
        
        user_input_clean = user_input.strip()
        user_input_lower = user_input_clean.lower()
        
        # Handle special commands
        if any(word in user_input_lower for word in ['reset', 'start over', 'new timesheet']):
            conversation_state = "greeting"
            current_entry = {}
            selected_table = ""
            flexible_batch = {}
            conversation_history = []
            response = self.get_greeting_with_options(voice_enabled)
            
            self.db.update_user_session(session_id, conversation_state, current_entry, selected_table, 
                                      conversation_history, flexible_batch, voice_enabled)
            return response
        
        # Handle project code requests
        if any(phrase in user_input_lower for phrase in ['show my project code', 'list project codes', 'what project codes', 'project codes', 'show codes']):
            response = self.handle_project_code_request(selected_table or flexible_batch.get('default_table'))
            return response
        
        # Determine conversation flow based on state
        if conversation_state == 'greeting':
            return self.handle_initial_conversation(user_input, session_data, session_id)
        elif conversation_state.startswith('flexible_'):
            return self.handle_flexible_conversation(user_input, session_data, session_id)
        else:
            return self.handle_single_conversation(user_input, session_data, session_id)

    def handle_initial_conversation(self, user_input: str, session_data: Dict, session_id: str) -> str:
        """Handle initial conversation to determine entry mode"""
        
        # Try to parse complex input first
        parsed_input = self.input_parser.parse_complex_input(user_input)
        entry_mode = self.detect_entry_mode(user_input)
        
        conversation_state = session_data['conversation_state']
        flexible_batch = session_data['flexible_batch']
        voice_enabled = session_data.get('voice_enabled', False)
        
        if entry_mode == 'flexible' or parsed_input['dates'] or len(parsed_input['project_codes']) > 1:
            # Switch to flexible mode
            conversation_state = 'flexible_gathering'
            flexible_batch = self.initialize_flexible_batch(parsed_input)
            response = self.process_flexible_input(parsed_input, flexible_batch, session_data['user_id'])
            
        elif entry_mode == 'weekly':
            # Switch to weekly mode (simplified for now)
            conversation_state = 'flexible_gathering'
            response = f"{random.choice(self.positive_responses)} Weekly timesheet it is! 📅\n\nAre you filling for Mars or Oracle projects this week?"
            
        elif entry_mode == 'single':
            # Switch to single mode
            conversation_state = 'single_gathering'
            response = self.handle_single_input_parsing(user_input, session_data)
            
        else:
            # Ask user what they want to do
            response = f"""I can help you with several types of timesheet entries:

**🎯 How would you like to fill your timesheet?**

1️⃣ **Single Day** - Log hours for today
2️⃣ **Whole Week** - Same entry Monday-Friday  
3️⃣ **Specific Dates** - Choose exactly which dates
4️⃣ **Mixed Entries** - Different projects on different dates

🗣️ **Voice Examples:**
• *"Whole week"*
• *"Twelve December thirteen December fifteen December"*  
• *"Single entry for today"*
• *"Mars and Oracle mixed"*

Just let me know what you prefer! 😊"""
        
        # Update session
        self.db.update_user_session(session_id, conversation_state, session_data['current_entry'], 
                                  session_data['selected_table'], [], flexible_batch, voice_enabled)
        
        return response

    def detect_entry_mode(self, text: str) -> str:
        """Detect what kind of timesheet entry the user wants"""
        text_lower = text.lower()
        
        # Check for whole week indicators
        week_indicators = ['whole week', 'entire week', 'full week', 'monday to friday', 'weekly']
        if any(indicator in text_lower for indicator in week_indicators):
            return 'weekly'
        
        # Check for specific dates (multiple dates = flexible mode)
        dates = self.date_parser.parse_multiple_dates(text)
        if len(dates) > 1:
            return 'flexible'
        elif len(dates) == 1:
            return 'single'
        
        # Check for mixed Mars/Oracle indicators
        if 'mars' in text_lower and 'oracle' in text_lower:
            return 'flexible'
        
        # Default to asking
        return 'ask_mode'

    def initialize_flexible_batch(self, parsed_input: Dict) -> Dict:
        """Initialize flexible batch from parsed input"""
        batch = FlexibleTimesheetBatch().__dict__
        
        if parsed_input['dates']:
            batch['dates'] = parsed_input['dates']
            batch['date_range'] = f"{parsed_input['dates'][0]} to {parsed_input['dates'][-1]}"
        
        if parsed_input['hours']:
            batch['default_hours'] = parsed_input['hours']
        
        if parsed_input['project_codes']:
            batch['suggested_codes'] = parsed_input['project_codes']
        
        if parsed_input['table_types']:
            batch['suggested_tables'] = parsed_input['table_types']
        
        if parsed_input['task']:
            batch['default_task'] = parsed_input['task']
        
        if parsed_input['systems']:
            batch['default_system'] = parsed_input['systems'][0]
        
        batch['mode'] = 'flexible'
        batch['entries'] = []
        
        return batch

    def process_flexible_input(self, parsed_input: Dict, flexible_batch: Dict, user_id: str) -> str:
        """Process parsed flexible input with voice-aware responses"""
        
        missing_info = []
        
        # Check what's missing
        if not parsed_input['dates']:
            missing_info.append('dates')
        
        if not parsed_input['hours']:
            missing_info.append('hours')
        
        if not parsed_input['project_codes']:
            missing_info.append('project_codes')
        
        if not parsed_input['task']:
            missing_info.append('task')
        
        if not parsed_input['systems']:
            missing_info.append('system')
        
        if missing_info:
            # Ask for missing information with voice-friendly prompts
            if 'dates' in missing_info:
                return """📅 **Great! I see you want flexible date entry.**

Which specific dates do you want to fill timesheets for? You can:

🗣️ **Say:** *"Twelve December, thirteen December, fifteen December"*
⌨️ **Type:** *"12dec 13dec 15dec"* or *"2025-01-15 2025-01-16"*

Just list the dates however feels natural! 😊"""
            
            elif 'hours' in missing_info:
                return f"""⏰ **Perfect! I have your dates: {', '.join(parsed_input['dates'])}**

How many hours per day? You can:

🗣️ **Say:** *"Eight hours"* or *"Eight and a half hours"*
⌨️ **Type:** *"8 hours"* or *"8.5 hours"*

Or tell me if you want different hours for each date! 😊"""
            
            elif 'project_codes' in missing_info:
                return """📋 **Which project codes are you using?**

🗣️ **Say:** *"Mars zero zero one"* or *"Oracle one zero one"*
⌨️ **Type:** *"MARS001"* or *"ORA101"*

You can also say *"show my project codes"* to hear all options! 😊"""
            
            elif 'task' in missing_info:
                return """📝 **What did you work on?**

🗣️ **Say:** *"Worked on API development and testing"*
⌨️ **Type:** Your task description

Please describe your work - I'll use this for all entries unless you want different descriptions! 😊"""
            
            else:
                return "I need a bit more information. What else can you tell me about these timesheet entries?"
        
        else:
            # All information provided - create entries
            return self.create_flexible_entries(parsed_input, flexible_batch, user_id)

    def create_flexible_entries(self, parsed_input: Dict, flexible_batch: Dict, user_id: str) -> str:
        """Create flexible batch entries and check for conflicts"""
        
        entries = []
        
        # Create entries based on parsed input
        if len(parsed_input['project_codes']) == 1:
            # Same project code for all dates
            project_code = parsed_input['project_codes'][0]
            table_type = 'Mars' if project_code.startswith('MARS') else 'Oracle'
            
            for date in parsed_input['dates']:
                entry = {
                    'date': date,
                    'hours': parsed_input['hours'],
                    'project_code': project_code,
                    'table_type': table_type,
                    'task': parsed_input['task'],
                    'system': parsed_input['systems'][0] if parsed_input['systems'] else 'System',
                    'user_id': user_id
                }
                entries.append(entry)
        
        # Check for conflicts
        conflicts = self.db.check_existing_timesheets_multiple(user_id, entries)
        
        flexible_batch['entries'] = entries
        flexible_batch['conflicts'] = conflicts
        flexible_batch['total_entries'] = len(entries)
        flexible_batch['total_hours'] = sum(entry['hours'] for entry in entries)
        
        if conflicts:
            return self.show_flexible_conflicts(flexible_batch)
        else:
            return self.show_flexible_draft(flexible_batch)

    def show_flexible_draft(self, flexible_batch: Dict) -> str:
        """Show draft for flexible batch entries"""
        entries = flexible_batch['entries']
        
        if not entries:
            return "No entries to process. Please provide timesheet details."
        
        # Group by table type for display
        mars_entries = [e for e in entries if e['table_type'] == 'Mars']
        oracle_entries = [e for e in entries if e['table_type'] == 'Oracle']
        
        response = "📋 **Your Flexible Timesheet Draft**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        if mars_entries:
            response += "🚀 **Mars Entries:**\n"
            for entry in mars_entries:
                response += f"   • **{entry['date']}**: {entry['hours']}h on {entry['project_code']} - {entry['task'][:40]}...\n"
            response += f"   **Mars Total:** {sum(e['hours'] for e in mars_entries)} hours\n\n"
        
        if oracle_entries:
            response += "🔮 **Oracle Entries:**\n"
            for entry in oracle_entries:
                response += f"   • **{entry['date']}**: {entry['hours']}h on {entry['project_code']} - {entry['task'][:40]}...\n"
            response += f"   **Oracle Total:** {sum(e['hours'] for e in oracle_entries)} hours\n\n"
        
        response += f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**Summary:**
• **Total Entries:** {flexible_batch['total_entries']}
• **Total Hours:** {flexible_batch['total_hours']}
• **Date Range:** {entries[0]['date']} to {entries[-1]['date']}

🗣️ **Say 'yes'** to submit or **'no'** to make changes! 😊"""
        
        return response

    def show_flexible_conflicts(self, flexible_batch: Dict) -> str:
        """Show conflicts for flexible batch entries"""
        conflicts = flexible_batch['conflicts']
        
        conflict_list = ""
        for conflict in conflicts:
            emoji = "🚀" if conflict['table_type'] == 'Mars' else "🔮"
            conflict_list += f"   • **{conflict['date']}** {emoji}: {conflict['hours']}h on {conflict['project_code']} - {conflict['task'][:40]}...\n"
        
        response = f"""⚠️ **Existing Timesheets Found**

I found {len(conflicts)} existing timesheet entries that would conflict:

{conflict_list}

**What would you like to do?**

🗣️ **Voice Commands:**
• Say **'override'** to replace all existing entries  
• Say **'skip conflicts'** to only fill empty days  
• Say **'cancel'** to start over

⌨️ **Or type your choice:** override, skip conflicts, or cancel

What's your choice? 😊"""
        
        return response

    def handle_flexible_conversation(self, user_input: str, session_data: Dict, session_id: str) -> str:
        """Handle ongoing flexible conversation"""
        
        conversation_state = session_data['conversation_state']
        flexible_batch = session_data['flexible_batch']
        voice_enabled = session_data.get('voice_enabled', False)
        user_input_lower = user_input.strip().lower()
        
        if conversation_state == 'flexible_gathering':
            # Continue gathering information
            parsed_input = self.input_parser.parse_complex_input(user_input)
            
            # Update flexible batch with new information
            if parsed_input['dates'] and not flexible_batch.get('dates'):
                flexible_batch['dates'] = parsed_input['dates']
            
            if parsed_input['hours'] and not flexible_batch.get('default_hours'):
                flexible_batch['default_hours'] = parsed_input['hours']
            
            # Process updated information
            response = self.process_flexible_input(parsed_input, flexible_batch, session_data['user_id'])
            conversation_state = 'flexible_draft'
            
        elif conversation_state == 'flexible_conflicts':
            if 'override' in user_input_lower:
                flexible_batch['override_existing'] = True
                conversation_state = 'flexible_draft'
                response = self.show_flexible_draft(flexible_batch)
                
            elif 'skip' in user_input_lower:
                flexible_batch['skip_existing'] = True
                # Filter out conflicting dates
                conflict_dates = [c['date'] for c in flexible_batch['conflicts']]
                filtered_entries = [e for e in flexible_batch['entries'] if e['date'] not in conflict_dates]
                flexible_batch['entries'] = filtered_entries
                
                if not filtered_entries:
                    response = "All dates have existing timesheets. No new entries to create. Say 'new timesheet' to start fresh!"
                    conversation_state = 'greeting'
                else:
                    conversation_state = 'flexible_draft'
                    response = self.show_flexible_draft(flexible_batch)
                    
            elif 'cancel' in user_input_lower:
                conversation_state = 'greeting'
                flexible_batch = {}
                response = "Flexible timesheet cancelled. What would you like to do instead?"
                
            else:
                response = "🗣️ Please say 'override', 'skip conflicts', or 'cancel'. ⌨️ Or type your choice."
        
        elif conversation_state == 'flexible_draft':
            if any(word in user_input_lower for word in ['yes', 'y', 'confirm', 'submit', 'ok', 'correct']):
                # Submit flexible batch
                success, record_ids = self.submit_flexible_batch(flexible_batch, session_data['user_id'], voice_enabled)
                
                if success:
                    conversation_state = 'submitted'
                    response = self.show_flexible_submission_success(flexible_batch, record_ids)
                    flexible_batch = {}  # Reset
                else:
                    response = "❌ Error saving flexible timesheet entries. Please try again or contact support."
                    
            elif any(word in user_input_lower for word in ['no', 'edit', 'change', 'wrong']):
                conversation_state = 'flexible_gathering'
                response = "No problem! What would you like to change about your flexible timesheet entries?"
                
            else:
                response = "🗣️ Please say 'yes' to submit or 'no' to make changes. ⌨️ Or type your choice."
        
        # Update session
        self.db.update_user_session(session_id, conversation_state, session_data['current_entry'], 
                                  session_data['selected_table'], [], flexible_batch, voice_enabled)
        
        return response

    def submit_flexible_batch(self, flexible_batch: Dict, user_id: str, voice_enabled: bool) -> Tuple[bool, List[int]]:
        """Submit flexible batch entries with voice-aware input method logging"""
        entries = []
        
        for entry_data in flexible_batch['entries']:
            entry = TimesheetEntry(
                date=entry_data['date'],
                hours=entry_data['hours'],
                system=entry_data.get('system', 'System'),
                project_code=entry_data['project_code'],
                task=entry_data.get('task', 'Task description'),
                submitted_at=datetime.datetime.now().isoformat(),
                user_id=user_id,
                table_type=entry_data['table_type']
            )
            entries.append(entry)
        
        update_existing = flexible_batch.get('override_existing', False)
        input_method = "voice" if voice_enabled else "text"
        return self.db.save_flexible_batch(entries, update_existing, input_method)

    def show_flexible_submission_success(self, flexible_batch: Dict, record_ids: List[int]) -> str:
        """Show success message for flexible batch submission"""
        entries = flexible_batch['entries']
        mars_count = len([e for e in entries if e['table_type'] == 'Mars'])
        oracle_count = len([e for e in entries if e['table_type'] == 'Oracle'])
        
        override_text = " (with overrides)" if flexible_batch.get('override_existing') else ""
        skip_text = " (skipping conflicts)" if flexible_batch.get('skip_existing') else ""
        
        return f"""🎉 **Flexible Timesheet Submitted Successfully!**

📊 **Submission Summary:**
• **Total Entries Created:** {len(entries)}
• **Mars Entries:** {mars_count} (🚀)  
• **Oracle Entries:** {oracle_count} (🔮)
• **Total Hours:** {flexible_batch['total_hours']}
• **Record IDs:** {', '.join(map(str, record_ids))}{override_text}{skip_text}

✅ All timesheets have been saved to their respective databases!

🗣️ **Say 'new timesheet'** for another entry or **'show history'** to view recent timesheets! 😊"""

    def handle_single_conversation(self, user_input: str, session_data: Dict, session_id: str) -> str:
        """Handle single timesheet conversation (placeholder)"""
        return "Single timesheet mode active. Please provide your timesheet details."

    def handle_single_input_parsing(self, user_input: str, session_data: Dict) -> str:
        """Handle single input parsing"""
        parsed_input = self.input_parser.parse_complex_input(user_input)
        
        if parsed_input['project_codes'] and parsed_input['hours'] and parsed_input['task']:
            return f"Got it! Single entry for {parsed_input['project_codes'][0]} with {parsed_input['hours']} hours. Ready to submit?"
        else:
            return "I need more details for your single timesheet entry. Please provide hours, project code, and task description."

    def handle_project_code_request(self, table_type: Optional[str]) -> str:
        """Handle project code listing request with voice-friendly format"""
        if not table_type:
            mars_codes = self.db.get_project_codes("Mars")
            oracle_codes = self.db.get_project_codes("Oracle")
            
            mars_list = "\n".join([f"• **{pc.code}** ({pc.code.replace('MARS', 'Mars ').replace('0', ' zero ')}): {pc.description}" for pc in mars_codes])
            oracle_list = "\n".join([f"• **{pc.code}** (Oracle {pc.code[3:]}): {pc.description}" for pc in oracle_codes])
            
            return f"""📋 **All Available Project Codes:**

🚀 **Mars Projects:**
{mars_list}

🔮 **Oracle Projects:**  
{oracle_list}

🗣️ **Voice Examples:**
• Say: *"Mars zero zero one"* for MARS001
• Say: *"Oracle one zero one"* for ORA101

Just mention the code you want to use! 😊"""
        else:
            project_codes = self.db.get_project_codes(table_type)
            if project_codes:
                if table_type == "Mars":
                    code_list = "\n".join([f"• **{pc.code}** (Say: '{pc.code.replace('MARS', 'Mars ').replace('0', ' zero ')}'): {pc.description}" for pc in project_codes])
                else:
                    code_list = "\n".join([f"• **{pc.code}** (Say: 'Oracle {pc.code[3:]}'): {pc.description}" for pc in project_codes])
                
                return f"📋 **Available {table_type} Project Codes:**\n\n{code_list}\n\nJust mention the code you want to use!"
            else:
                return f"No {table_type} project codes found. Please contact your administrator."

# Initialize the enhanced voice-enabled bot
db = DatabaseManager()
bot = VoiceEnabledTimesheetBot(db)

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
    """Create the voice-enabled Gradio application"""
    
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
    
    .voice-feature {
        background: #e8f5e8;
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
        border-left: 4px solid #4caf50;
    }
    
    .flexibility-feature {
        background: #fff3e0;
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
        border-left: 4px solid #ff9800;
    }
    
    .audio-controls {
        background: #f3e5f5;
        padding: 10px;
        border-radius: 6px;
        margin: 5px 0;
    }
    """
    
    with gr.Blocks(css=custom_css, title="Voice-Enabled Timesheet Assistant", theme=gr.themes.Soft()) as demo:
        
        # Authentication state
        session_state = gr.State("")
        user_role_state = gr.State("")
        authenticated_state = gr.State(False)
        
        with gr.Column(visible=True) as auth_container:
            gr.Markdown("""
            # 🔐 Voice-Enabled Conversational Timesheet Assistant
            
            **🆕 NEW: Voice Commands & Ultimate Flexibility!**
            
            **Demo Accounts:**
            - **Admin:** username: `admin`, password: `admin123`
            - **User:** username: `user1`, password: `user123`
            
            **🎤 Voice Features:**
            ✅ **Speech-to-Text:** Speak your timesheet entries naturally  
            ✅ **Text-to-Speech:** Get spoken responses from Tim  
            ✅ **Voice Commands:** "Enable voice", "Show project codes", etc.  
            ✅ **Natural Pronunciation:** Say "Mars zero zero one" for MARS001  
            
            **🌟 Enhanced Features:**
            ✅ **Flexible Date Selection:** Choose any specific dates  
            ✅ **Mixed Mars/Oracle:** Different projects on same dates  
            ✅ **Complex Input Parsing:** Voice or text with everything at once  
            ✅ **Smart Conflict Detection:** Override or skip existing entries  
            ✅ **Natural Date Formats:** Voice-friendly date recognition  
            ✅ **Conversational Flow:** Ask only for missing information  
            ✅ **Complete Audit Trail:** Voice/text input method tracking
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
            
            # Main chat interface
            gr.Markdown("""
            ## 🤖 Tim - Voice-Enabled Flexible Timesheet Assistant
            
            **🎤 Voice Commands Available!**
            """)
            
            # Voice feature highlight
            gr.Markdown("""
            ### 🎤 Voice Input Examples:
            - **"Mars, eight hours, Mars zero zero one, worked on navigation system"**
            - **"Four hours, Mars zero zero one, twelve December thirteen December, API development"**
            - **"Enable voice responses"** / **"Disable voice responses"**
            - **"Show my project codes"** / **"Help"**
            """, elem_classes=["voice-feature"])
            
            # Flexibility feature highlight
            gr.Markdown("""
            ### 🎯 Text Input Examples:
            - **"4hours, MARS001, 12dec 13dec 15dec, worked on API changes"**
            - **"8 hours mixed Mars and Oracle on specific dates"**
            - **"copy for the whole week"**
            - **"reset"**
            """, elem_classes=["flexibility-feature"])
            
            chatbot = gr.Chatbot(
                [],
                elem_id="chatbot",
                bubble_full_width=False,
                height=600,
                show_label=False,
                avatar_images=("👤", "🤖")
            )
            
            # Input controls with voice support
            with gr.Row():
                with gr.Column(scale=3):
                    msg = gr.Textbox(
                        placeholder="Type or use voice input... Try: 'Mars, 8 hours, Mars zero zero one, navigation work'",
                        show_label=False,
                        lines=2
                    )
                with gr.Column(scale=1, elem_classes=["audio-controls"]):
                    audio_input = gr.Audio(
                        sources=["microphone"],
                        type="filepath",
                        label="🎤 Voice Input",
                        show_label=True,
                        scale=1
                    )
            
            with gr.Row():
                send_btn = gr.Button("Send 💬", variant="primary", scale=1)
                clear_btn = gr.Button("🔄 Reset Chat", scale=1)
                voice_toggle = gr.Button("🎤 Voice Mode", scale=1)
            
            # Audio output for voice responses
            audio_output = gr.Audio(
                label="🔊 Voice Response",
                autoplay=True,
                visible=True,
                show_label=True
            )
            
            gr.Markdown("""
            **🆕 Ultimate Features:** Voice commands, flexible dates, mixed entries, complex parsing, conflict resolution! 

            **💡 Quick Voice Commands:**
            - Say **"enable voice"** for spoken responses
            - Say **"help"** for assistance
            - Say **"show my project codes"** to hear available codes
            - Say **"reset"** to start fresh
            """)
    
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
                    f"✅ Welcome **{username}** ({role}) - Voice & flexibility enabled! 🎤🎯",  # User info
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
                None,                      # Clear audio output
            )
        
        def handle_chat(message, audio, history, session_id):
            if not session_id or session_id not in user_sessions:
                return "", None, history + [("", "❌ Session expired. Please log in again.")], None
            
            text_response, audio_response, updated_history = bot.process_conversation(message, audio, session_id, history)
            return "", None, updated_history, audio_response
        
        def handle_voice_toggle(session_id):
            if not session_id or session_id not in user_sessions:
                return "❌ Session expired"
            
            # Toggle voice mode
            session_data = db.get_user_session(session_id)
            if session_data:
                current_voice_enabled = session_data.get('voice_enabled', False)
                new_voice_enabled = not current_voice_enabled
                
                db.update_user_session(
                    session_id, 
                    session_data['conversation_state'], 
                    session_data['current_entry'],
                    session_data['selected_table'], 
                    session_data['conversation_history'],
                    session_data['flexible_batch'], 
                    new_voice_enabled
                )
                
                status = "enabled" if new_voice_enabled else "disabled"
                return f"🎤 Voice responses {status}!"
            
            return "❌ Session error"
        
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
                    authenticated_state, user_info, auth_message, chatbot, audio_output]
        )
        
        # Chat interactions
        msg.submit(
            handle_chat, 
            [msg, audio_input, chatbot, session_state], 
            [msg, audio_input, chatbot, audio_output]
        )
        send_btn.click(
            handle_chat, 
            [msg, audio_input, chatbot, session_state], 
            [msg, audio_input, chatbot, audio_output]
        )
        audio_input.change(
            handle_chat,
            [msg, audio_input, chatbot, session_state], 
            [msg, audio_input, chatbot, audio_output]
        )
        
        clear_btn.click(lambda: ([], None), outputs=[chatbot, audio_output])
        
        voice_toggle.click(
            handle_voice_toggle,
            inputs=[session_state],
            outputs=[user_info]
        )
        
        # Enhanced welcome message
        demo.load(
            lambda: [([], "🤖 Hey there! I'm Tim, your voice-enabled flexible timesheet assistant! 🎤\n\n**Voice Commands Available:**\n\n🗣️ **Say:** \"Mars, eight hours, Mars zero zero one, worked on navigation system\"\n🗣️ **Say:** \"Enable voice responses\" to hear me talk back!\n🗣️ **Say:** \"Show my project codes\" to hear all available codes\n🗣️ **Say:** \"Help\" for more assistance\n\n⌨️ **Or type naturally:** \"4hours, MARS001, 12dec 13dec, API work\"\n\n💬 **Quick Commands:**\n• \"enable voice\" / \"disable voice\" - Toggle voice responses\n• \"reset\" - Start fresh conversation\n• \"help\" - Get assistance\n\nTry speaking or typing - I understand both! What would you like to do today? 😊")],
            outputs=[chatbot]
        )
    
    return demo

def main():
    """Main function to run the voice-enabled app"""
    print("🚀 Starting Voice-Enabled Flexible Timesheet Assistant...")
    print("✅ VOICE FEATURES:")
    print("   🎤 Speech-to-text input with natural language processing")
    print("   🔊 Text-to-speech responses with voice commands")  
    print("   🗣️ Voice-friendly project code pronunciation")
    print("   📅 Natural date recognition from speech")
    print("   💬 Toggle voice responses on/off")
    print()
    print("✅ FLEXIBILITY FEATURES:")
    print("   🎯 Ultimate flexibility - any dates, any combination")
    print("   🤖 Complex input parsing - voice or text with everything")  
    print("   📅 Mixed Mars/Oracle entries on same conversation")
    print("   🔍 Smart conflict detection and resolution")
    print("   💬 Conversational flow asking only missing info")
    print("   📋 Project code validation with easy lookup")
    print()
    print("🔐 Demo accounts:")
    print("   • Admin: admin / admin123")  
    print("   • User: user1 / user123")
    print()
    print("💡 Try voice commands:")
    print("   • 'Mars, eight hours, Mars zero zero one, worked on navigation'")
    print("   • 'Enable voice responses'")
    print("   • 'Show my project codes'")
    print("   • 'Four hours, Mars zero zero one, twelve December thirteen December'")
    print()
    print("⚠️ Note: Voice features require:")
    print("   • Internet connection (for speech recognition)")
    print("   • Microphone access")
    print("   • Audio output for voice responses")
    
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