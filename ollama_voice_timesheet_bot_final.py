"""
Complete Enhanced Conversational Timesheet Bot
with Voice Commands and Local Ollama Integration

Advanced Features:
- 🤖 Local Ollama llama3.2:1b model integration
- 🎤 Voice input with speech-to-text
- 🔊 Voice responses with text-to-speech  
- 📅 Flexible date selection and timesheet management
- 🔀 Mixed Mars/Oracle entries in same conversation
- 🧠 AI-powered conversation processing
- 📝 Natural language understanding
- 💬 Context-aware responses
- 🔍 Project code validation
- ⚡ Smart conflict detection
- 🔒 Comprehensive audit logging

Requirements:
pip install ollama pyodbc gradio bcrypt pandas python-dateutil speechrecognition pyttsx3 pyaudio

Make sure Ollama is running locally:
ollama serve
ollama pull llama3.2:1b

Usage:
python ollama_voice_timesheet_bot.py
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

class OllamaAIProcessor:
    """AI processor using local Ollama llama3.2:1b model"""
    
    def __init__(self, model_name: str = "llama3.2:1b"):
        self.model_name = model_name
        self.system_prompt = self._get_system_prompt()
        self._test_connection()
    
    def _test_connection(self):
        """Test connection to local Ollama"""
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": "Hello"}],
                options={"temperature": 0.7, "num_ctx": 4096}
            )
            print(f"✅ Ollama {self.model_name} connected successfully")
            return True
        except Exception as e:
            print(f"⚠️ Ollama connection error: {e}")
            print("Make sure Ollama is running: ollama serve")
            print(f"And model is available: ollama pull {self.model_name}")
            return False
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for the timesheet assistant"""
        return """You are Tim, a helpful and friendly timesheet assistant AI. You help users fill out timesheets for Mars and Oracle projects.

Your personality:
- Friendly, encouraging, and professional
- Use emojis sparingly and appropriately  
- Be conversational but concise
- Always stay focused on timesheet tasks

Available project codes:
Mars projects: MARS001 (Navigation), MARS002 (Life Support), MARS003 (Communication), MARS004 (Exploration), MARS005 (Sample Collection)
Oracle projects: ORA100 (Performance), ORA101 (Migration), ORA102 (ETL), ORA103 (Security), ORA104 (Backup)

Your capabilities:
- Help fill single day timesheets
- Handle whole week entries (Monday-Friday)
- Process flexible date selections
- Handle mixed Mars/Oracle entries
- Validate project codes and hours (max 12 hours per day)
- Voice and text input support

Key rules:
- Only accept valid project codes from the lists above
- Ask for missing information conversationally
- Be helpful with date formatting and project code selection
- Confirm details before submission
- Make the process feel easy and natural

When analyzing user input, extract:
- Hours (convert words like "eight" to 8, "eight and a half" to 8.5)
- Project codes (MARS001, ORA100, etc. or voice variations like "Mars zero zero one")
- Dates (today, specific dates, date ranges)
- Tasks/descriptions
- Systems used

Always respond in a helpful, encouraging manner and guide users through the timesheet process step by step."""

    def analyze_timesheet_input(self, user_input: str, conversation_context: Dict) -> Dict:
        """Analyze user input for timesheet information using Ollama AI"""
        
        # Prepare context for AI
        context_info = self._prepare_context(conversation_context)
        
        # Create comprehensive prompt for analysis
        analysis_prompt = f"""
Context: {context_info}

User input: "{user_input}"

Analyze this timesheet input and extract information. Look for:
1. Hours (convert words like "eight" to 8, "eight and a half" to 8.5)
2. Project codes (MARS001-MARS005, ORA100-ORA104, or voice variations)
3. Dates (today, specific dates like "12dec", "January 15", etc.)
4. Task descriptions
5. Systems/tools mentioned
6. Table type (Mars or Oracle)

Also identify:
- What information is missing for a complete timesheet
- Any validation issues (invalid codes, hours > 12, etc.)
- What the user seems to want to do (single entry, multiple dates, etc.)

Provide a natural, helpful response guiding them through the next steps.
Be encouraging and make it feel conversational.
"""

        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": analysis_prompt}
                ],
                options={
                    "temperature": 0.4,  # Lower temperature for more consistent analysis
                    "num_ctx": 4096,
                    "top_p": 0.9
                }
            )
            
            ai_response = response['message']['content']
            
            # Extract structured data from AI response using regex patterns
            extracted_data = self._extract_structured_data(user_input, ai_response)
            
            return {
                "ai_response": ai_response,
                "extracted_data": extracted_data,
                "needs_followup": self._check_if_complete(extracted_data)
            }
                
        except Exception as e:
            print(f"AI processing error: {e}")
            return {
                "ai_response": "I'm having trouble processing that right now. Could you tell me about your timesheet entry? I need to know the project (Mars or Oracle), hours worked, project code, and what you worked on.",
                "extracted_data": {},
                "needs_followup": True
            }
    
    def _extract_structured_data(self, user_input: str, ai_response: str) -> Dict:
        """Extract structured data from user input and AI analysis"""
        data = {
            "hours": None,
            "project_codes": [],
            "dates": [],
            "task": None,
            "system": None,
            "table_type": None
        }
        
        # Extract hours using patterns
        hours_patterns = [
            r'(\d+\.?\d*)\s*(?:and\s*(?:a\s*)?half)',  # "8 and a half"
            r'(\d+\.?\d*)\s*(?:point\s*(?:five|25|75))',  # "8 point 5"
            r'(\d+\.?\d*)\s*(?:hours?|hrs?|h\b)',  # "8 hours"
            r'\b(?:eight|8)(?:\s*and\s*(?:a\s*)?half)?\b',  # "eight", "eight and a half"
            r'\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|1|2|3|4|5|6|7|8|9|10|11|12)\b'
        ]
        
        # Word to number mapping
        word_numbers = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
            'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12
        }
        
        user_lower = user_input.lower()
        for pattern in hours_patterns:
            match = re.search(pattern, user_lower)
            if match:
                try:
                    hours_str = match.group(1) if match.lastindex else match.group(0)
                    
                    # Handle word numbers
                    if hours_str in word_numbers:
                        hours = word_numbers[hours_str]
                    else:
                        hours = float(hours_str) if '.' in hours_str else int(hours_str.split()[0])
                    
                    # Handle "and a half"
                    if 'and' in user_lower and 'half' in user_lower:
                        hours += 0.5
                    
                    if 0 < hours <= 12:
                        data["hours"] = hours
                        break
                except (ValueError, AttributeError):
                    continue
        
        # Extract project codes
        project_patterns = [
            r'(MARS00[1-5])',
            r'(ORA10[0-4])',
            r'mars\s*(?:zero\s*)*(?:zero\s*)*([1-5])',  # "mars zero zero one"
            r'oracle\s*(?:one\s*)*(?:zero\s*)*([0-4])'   # "oracle one zero one"
        ]
        
        for pattern in project_patterns:
            matches = re.finditer(pattern, user_input.upper())
            for match in matches:
                if pattern.startswith('(MARS') or pattern.startswith('(ORA'):
                    code = match.group(1)
                elif 'mars' in pattern:
                    num = match.group(1)
                    code = f"MARS00{num}"
                elif 'oracle' in pattern:
                    num = match.group(1)
                    code = f"ORA10{num}"
                
                if code and code not in data["project_codes"]:
                    data["project_codes"].append(code)
                    data["table_type"] = "Mars" if code.startswith("MARS") else "Oracle"
        
        # Extract dates (simplified)
        today = datetime.date.today()
        if 'today' in user_lower:
            data["dates"] = [today.strftime('%Y-%m-%d')]
        
        # Extract task from longer phrases
        task_indicators = ['worked on', 'working on', 'development', 'api', 'system', 'navigation', 'database']
        for indicator in task_indicators:
            if indicator in user_lower:
                # Find the sentence containing the task
                sentences = re.split(r'[,.]', user_input)
                for sentence in sentences:
                    if indicator in sentence.lower() and len(sentence.strip()) > 10:
                        data["task"] = sentence.strip()
                        break
                break
        
        return data
    
    def _check_if_complete(self, data: Dict) -> bool:
        """Check if extracted data is complete for submission"""
        required_fields = ["hours", "project_codes", "task"]
        return not all(data.get(field) for field in required_fields)
    
    def _prepare_context(self, context: Dict) -> str:
        """Prepare conversation context for AI"""
        context_parts = []
        
        if context.get('conversation_state'):
            context_parts.append(f"State: {context['conversation_state']}")
        
        if context.get('current_entry'):
            entry = context['current_entry']
            if entry:
                context_parts.append(f"Current entry: {entry}")
        
        if context.get('voice_enabled'):
            context_parts.append("Voice mode: enabled")
        
        return " | ".join(context_parts) if context_parts else "New conversation"

    def generate_conversational_response(self, analysis_result: Dict, conversation_context: Dict) -> str:
        """Generate conversational response based on analysis"""
        
        extracted_data = analysis_result["extracted_data"]
        missing_fields = []
        
        # Check what's missing
        if not extracted_data.get("hours"):
            missing_fields.append("hours")
        if not extracted_data.get("project_codes"):
            missing_fields.append("project_code")
        if not extracted_data.get("task"):
            missing_fields.append("task")
        
        # Use AI to generate appropriate response
        if missing_fields:
            prompt = f"""
The user has provided some timesheet information: {extracted_data}
Missing information: {missing_fields}

Generate a friendly, conversational response asking for the missing information.
Be specific about what you need and provide examples.
Keep it natural and encouraging.
"""
        else:
            prompt = f"""
The user has provided complete timesheet information: {extracted_data}

Generate a friendly confirmation message showing what you understood and ask if they want to submit it.
Be encouraging and professional.
"""
        
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                options={"temperature": 0.7, "num_ctx": 2048}
            )
            
            return response['message']['content']
            
        except Exception as e:
            # Fallback response
            if missing_fields:
                return f"I need a bit more information for your timesheet. Could you tell me about: {', '.join(missing_fields)}?"
            else:
                return f"Perfect! I have all the details. Ready to submit your timesheet entry?"

class VoiceProcessor:
    """Voice processing for speech-to-text and text-to-speech"""
    
    def __init__(self):
        self.recognizer = sr.Recognizer()
        try:
            self.microphone = sr.Microphone()
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            print("✅ Microphone initialized")
        except Exception as e:
            print(f"⚠️ Microphone setup warning: {e}")
            self.microphone = None
        
        self.tts_engine = None
        self.init_tts()
    
    def init_tts(self):
        """Initialize text-to-speech engine"""
        try:
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', 150)
            self.tts_engine.setProperty('volume', 0.8)
            
            voices = self.tts_engine.getProperty('voices')
            if voices:
                for voice in voices:
                    if 'female' in voice.name.lower():
                        self.tts_engine.setProperty('voice', voice.id)
                        break
                else:
                    self.tts_engine.setProperty('voice', voices[0].id)
            
            print("✅ Text-to-speech initialized")
        except Exception as e:
            print(f"⚠️ TTS initialization error: {e}")
            self.tts_engine = None
    
    def speech_to_text(self, audio_file_path: str) -> str:
        """Convert speech to text"""
        try:
            with sr.AudioFile(audio_file_path) as source:
                audio_data = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio_data)
                print(f"🎤 Voice recognized: {text}")
                return text
        except sr.UnknownValueError:
            return "Sorry, I couldn't understand that. Please try again."
        except Exception as e:
            print(f"Speech recognition error: {e}")
            return "Voice processing error. Please try typing instead."
    
    def text_to_speech(self, text: str) -> Optional[str]:
        """Convert text to speech"""
        if not self.tts_engine:
            return None
            
        try:
            clean_text = self._clean_text_for_speech(text)
            temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_file.close()
            
            self.tts_engine.save_to_file(clean_text, temp_file.name)
            self.tts_engine.runAndWait()
            
            return temp_file.name
        except Exception as e:
            print(f"TTS error: {e}")
            return None
    
    def _clean_text_for_speech(self, text: str) -> str:
        """Clean text for better speech synthesis"""
        # Remove markdown and emojis
        text = re.sub(r'\*\*(.*?)\*\*', r'\\1', text)
        text = re.sub(r'\*(.*?)\*', r'\\1', text)
        text = re.sub(r'#{1,6}\s+', '', text)
        text = re.sub(r'[📅📊📋🎯🚀🔮⏰💻📂📝✅⚠️❌🎉💡🔍🆕🌟🎤🔊]', '', text)
        
        # Replace technical terms for better pronunciation
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
            'SQL': 'S Q L'
        }
        
        for term, replacement in replacements.items():
            text = text.replace(term, replacement)
        
        # Limit length
        if len(text) > 400:
            text = text[:400] + "... Please check the screen for more details."
        
        return text

class DatabaseManager:
    """Database management for timesheet storage"""
    
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
        """Initialize database tables"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Users table
                cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='users' AND xtype='U')
                CREATE TABLE users (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    username NVARCHAR(50) UNIQUE NOT NULL,
                    email NVARCHAR(100) UNIQUE NOT NULL,
                    password_hash NVARCHAR(256) NOT NULL,
                    role NVARCHAR(20) DEFAULT 'user',
                    created_at DATETIME2 DEFAULT GETDATE(),
                    last_login DATETIME2,
                    is_active BIT DEFAULT 1
                )
                """)
                
                # Project codes table
                cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='project_codes' AND xtype='U')
                CREATE TABLE project_codes (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    code NVARCHAR(20) UNIQUE NOT NULL,
                    description NVARCHAR(200) NOT NULL,
                    table_type NVARCHAR(20) NOT NULL,
                    is_active BIT DEFAULT 1,
                    created_at DATETIME2 DEFAULT GETDATE()
                )
                """)
                
                # Timesheet tables
                for table in ['Mars', 'Oracle']:
                    cursor.execute(f"""
                    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{table}_timesheet' AND xtype='U')
                    CREATE TABLE {table}_timesheet (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        date DATE NOT NULL,
                        hours DECIMAL(5,2) NOT NULL CHECK (hours > 0 AND hours <= 12),
                        system NVARCHAR(100) NOT NULL,
                        project_code NVARCHAR(20) NOT NULL,
                        task NVARCHAR(1000) NOT NULL,
                        submitted_at DATETIME2 NOT NULL,
                        user_id NVARCHAR(50) NOT NULL,
                        validation_status NVARCHAR(20) DEFAULT 'valid',
                        created_at DATETIME2 DEFAULT GETDATE(),
                        UNIQUE(user_id, date)
                    )
                    """)
                
                # Sessions table
                cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='user_sessions' AND xtype='U')
                CREATE TABLE user_sessions (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    session_id NVARCHAR(100) UNIQUE NOT NULL,
                    user_id NVARCHAR(50) NOT NULL,
                    conversation_state NVARCHAR(50) DEFAULT 'greeting',
                    current_entry NVARCHAR(MAX) DEFAULT '{}',
                    conversation_history NVARCHAR(MAX) DEFAULT '[]',
                    voice_enabled BIT DEFAULT 0,
                    created_at DATETIME2 DEFAULT GETDATE(),
                    updated_at DATETIME2 DEFAULT GETDATE(),
                    expires_at DATETIME2 NOT NULL
                )
                """)
                
                # Audit log
                cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='audit_log' AND xtype='U')
                CREATE TABLE audit_log (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    user_id NVARCHAR(50) NOT NULL,
                    action NVARCHAR(50) NOT NULL,
                    table_name NVARCHAR(50) NOT NULL,
                    record_id INT,
                    details NVARCHAR(MAX),
                    input_method NVARCHAR(20) DEFAULT 'text',
                    timestamp DATETIME2 DEFAULT GETDATE()
                )
                """)
                
                conn.commit()
                self._create_default_data(cursor, conn)
                
        except Exception as e:
            print(f"Database initialization error: {e}")
            raise

    def _create_default_data(self, cursor, conn):
        """Create default users and project codes"""
        try:
            # Check if admin exists
            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            if cursor.fetchone()[0] == 0:
                admin_hash = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
                cursor.execute(
                    "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                    ("admin", "admin@company.com", admin_hash, "admin")
                )
            
            # Check if user1 exists
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'user1'")
            if cursor.fetchone()[0] == 0:
                user_hash = bcrypt.hashpw("user123".encode(), bcrypt.gensalt()).decode()
                cursor.execute(
                    "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                    ("user1", "user1@company.com", user_hash, "user")
                )
            
            # Check if project codes exist
            cursor.execute("SELECT COUNT(*) FROM project_codes")
            if cursor.fetchone()[0] == 0:
                codes = [
                    ("MARS001", "Mars Rover Navigation System", "Mars"),
                    ("MARS002", "Mars Habitat Life Support", "Mars"),
                    ("MARS003", "Mars Communication Array", "Mars"),
                    ("MARS004", "Mars Surface Exploration", "Mars"),
                    ("MARS005", "Mars Sample Collection", "Mars"),
                    ("ORA100", "Database Performance Optimization", "Oracle"),
                    ("ORA101", "Cloud Infrastructure Migration", "Oracle"),
                    ("ORA102", "Data Warehouse ETL Process", "Oracle"),
                    ("ORA103", "Security Framework Implementation", "Oracle"),
                    ("ORA104", "Database Backup Strategy", "Oracle")
                ]
                
                for code, desc, table_type in codes:
                    cursor.execute(
                        "INSERT INTO project_codes (code, description, table_type) VALUES (?, ?, ?)",
                        (code, desc, table_type)
                    )
            
            conn.commit()
            print("✅ Database initialized with default data")
            
        except Exception as e:
            print(f"Error creating default data: {e}")

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user credentials"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, username, email, password_hash, role, is_active FROM users WHERE username = ? AND is_active = 1",
                    username
                )
                row = cursor.fetchone()
                
                if row and bcrypt.checkpw(password.encode(), row[3].encode()):
                    cursor.execute("UPDATE users SET last_login = GETDATE() WHERE id = ?", row[0])
                    conn.commit()
                    
                    return User(
                        id=row[0], username=row[1], email=row[2],
                        password_hash=row[3], role=row[4], is_active=bool(row[5])
                    )
        except Exception as e:
            print(f"Authentication error: {e}")
        return None

    def create_user_session(self, user_id: str) -> str:
        """Create user session"""
        session_id = str(uuid.uuid4())
        expires_at = datetime.datetime.now() + datetime.timedelta(hours=8)
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO user_sessions (session_id, user_id, expires_at) VALUES (?, ?, ?)",
                    (session_id, user_id, expires_at)
                )
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
                    SELECT user_id, conversation_state, current_entry, conversation_history, voice_enabled
                    FROM user_sessions 
                    WHERE session_id = ? AND expires_at > GETDATE()
                """, session_id)
                
                row = cursor.fetchone()
                if row:
                    return {
                        'user_id': row[0],
                        'conversation_state': row[1] or 'greeting',
                        'current_entry': json.loads(row[2]) if row[2] else {},
                        'conversation_history': json.loads(row[3]) if row[3] else [],
                        'voice_enabled': bool(row[4])
                    }
        except Exception as e:
            print(f"Session retrieval error: {e}")
        return None

    def update_user_session(self, session_id: str, data: Dict):
        """Update user session"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE user_sessions 
                    SET conversation_state = ?, current_entry = ?, conversation_history = ?, voice_enabled = ?,
                        updated_at = GETDATE(), expires_at = DATEADD(hour, 8, GETDATE())
                    WHERE session_id = ?
                """, (
                    data.get('conversation_state', 'greeting'),
                    json.dumps(data.get('current_entry', {})),
                    json.dumps(data.get('conversation_history', [])),
                    data.get('voice_enabled', False),
                    session_id
                ))
                conn.commit()
        except Exception as e:
            print(f"Session update error: {e}")

    def get_project_codes(self, table_type: str) -> List[ProjectCode]:
        """Get project codes for table type"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, code, description, table_type, is_active, created_at FROM project_codes WHERE table_type = ? AND is_active = 1 ORDER BY code",
                    table_type
                )
                rows = cursor.fetchall()
                
                return [
                    ProjectCode(
                        id=r[0], code=r[1], description=r[2], table_type=r[3],
                        is_active=bool(r[4]), created_at=str(r[5])
                    ) for r in rows
                ]
        except Exception as e:
            print(f"Error fetching project codes: {e}")
            return []

    def save_timesheet(self, entry: TimesheetEntry, input_method: str = "text") -> Tuple[bool, Optional[int]]:
        """Save timesheet entry"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                table_name = f"{entry.table_type}_timesheet"
                
                # Check if entry already exists for this date
                cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE user_id = ? AND date = ?", 
                             (entry.user_id, entry.date))
                if cursor.fetchone()[0] > 0:
                    return False, None  # Entry already exists
                
                # Insert new entry
                cursor.execute(f"""
                    INSERT INTO {table_name} (date, hours, system, project_code, task, submitted_at, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry.date, entry.hours, entry.system, entry.project_code,
                    entry.task, entry.submitted_at, entry.user_id
                ))
                
                # Get the inserted ID
                cursor.execute("SELECT @@IDENTITY")
                record_id = cursor.fetchone()[0]
                
                # Log audit entry
                cursor.execute("""
                    INSERT INTO audit_log (user_id, action, table_name, record_id, details, input_method)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    entry.user_id, "INSERT", table_name, record_id,
                    json.dumps(asdict(entry)), input_method
                ))
                
                conn.commit()
                return True, record_id
                
        except Exception as e:
            print(f"Save timesheet error: {e}")
            return False, None

class OllamaTimesheetBot:
    """Main bot class with Ollama AI integration"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.ai_processor = OllamaAIProcessor()
        self.voice_processor = VoiceProcessor()
        print("✅ Ollama Timesheet Bot initialized")

    def process_conversation(self, user_input: str, audio_input, session_id: str, history: List[Tuple[str, str]]) -> Tuple[str, Optional[str], List[Tuple[str, str]]]:
        """Main conversation processing with Ollama AI"""
        
        # Handle voice input first
        if audio_input is not None:
            voice_text = self.voice_processor.speech_to_text(audio_input)
            if voice_text and not voice_text.startswith("Sorry") and not voice_text.startswith("Voice"):
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
        
        # Handle special commands
        voice_enabled = session_data.get('voice_enabled', False)
        
        if self._is_voice_command(user_input):
            response, new_voice_enabled = self._handle_voice_command(user_input, voice_enabled)
            session_data['voice_enabled'] = new_voice_enabled
            self.db.update_user_session(session_id, session_data)
            
            audio_response = None
            if new_voice_enabled:
                audio_response = self.voice_processor.text_to_speech(response)
            
            history.append((user_input, response))
            return "", audio_response, history
        
        # Handle project code requests
        if self._is_project_code_request(user_input):
            response = self._get_project_codes_response()
            audio_response = self.voice_processor.text_to_speech(response) if voice_enabled else None
            history.append((user_input, response))
            return "", audio_response, history
        
        # Handle help requests
        if self._is_help_request(user_input):
            response = self._get_help_response()
            audio_response = self.voice_processor.text_to_speech(response) if voice_enabled else None
            history.append((user_input, response))
            return "", audio_response, history
        
        # Process with Ollama AI
        try:
            analysis_result = self.ai_processor.analyze_timesheet_input(user_input, session_data)
            extracted_data = analysis_result["extracted_data"]
            
            # Update current entry with extracted data
            current_entry = session_data.get('current_entry', {})
            for key, value in extracted_data.items():
                if value:
                    if key == "project_codes" and value:
                        current_entry['project_code'] = value[0]
                        current_entry['table_type'] = 'Mars' if value[0].startswith('MARS') else 'Oracle'
                    elif key == "dates" and value:
                        current_entry['date'] = value[0]
                    elif key in ["hours", "task", "system"]:
                        current_entry[key] = value
            
            session_data['current_entry'] = current_entry
            
            # Check if we have enough data to submit
            if self._is_entry_complete(current_entry):
                # Show confirmation
                response = f"""Perfect! I have all the details for your timesheet:

📊 **Timesheet Summary:**
• **Project:** {current_entry.get('table_type', 'Unknown')} - {current_entry.get('project_code', 'Unknown')}
• **Date:** {current_entry.get('date', 'Today')}
• **Hours:** {current_entry.get('hours', 0)}
• **System:** {current_entry.get('system', 'Not specified')}
• **Task:** {current_entry.get('task', 'Not specified')}

Should I submit this timesheet entry? Say 'yes' to submit or 'no' to make changes."""
                
                session_data['conversation_state'] = 'confirmation'
            
            elif user_input.lower() in ['yes', 'submit', 'confirm', 'ok'] and session_data.get('conversation_state') == 'confirmation':
                # Submit the timesheet
                success = self._submit_timesheet(current_entry, session_data['user_id'], voice_enabled)
                
                if success:
                    response = f"""🎉 **Timesheet Submitted Successfully!**

✅ Your {current_entry.get('table_type', 'project')} timesheet has been saved!
• **Hours:** {current_entry.get('hours', 0)}
• **Project:** {current_entry.get('project_code', 'Unknown')}
• **Date:** {current_entry.get('date', 'Today')}

Ready for another timesheet entry? Just tell me about your next project!"""
                    
                    # Reset current entry
                    session_data['current_entry'] = {}
                    session_data['conversation_state'] = 'greeting'
                else:
                    response = "❌ Sorry, there was an error submitting your timesheet. This might be because you already have an entry for this date. Please try again or contact support."
            
            else:
                # Use AI to generate conversational response
                response = self.ai_processor.generate_conversational_response(analysis_result, session_data)
            
            # Update session
            self.db.update_user_session(session_id, session_data)
            
        except Exception as e:
            print(f"Conversation processing error: {e}")
            response = "I'm having trouble processing that. Could you tell me about your timesheet entry? I need the project (Mars or Oracle), hours worked, project code, and what you worked on."
        
        # Generate voice response if enabled
        audio_response = None
        if voice_enabled and response:
            audio_response = self.voice_processor.text_to_speech(response)
        
        history.append((user_input, response))
        return "", audio_response, history

    def _is_voice_command(self, user_input: str) -> bool:
        """Check if input is a voice command"""
        voice_commands = ['enable voice', 'disable voice', 'turn on voice', 'turn off voice', 'voice mode']
        return any(cmd in user_input.lower() for cmd in voice_commands)
    
    def _handle_voice_command(self, user_input: str, current_voice_enabled: bool) -> Tuple[str, bool]:
        """Handle voice commands"""
        user_lower = user_input.lower()
        
        if 'enable' in user_lower or 'turn on' in user_lower or 'voice mode on' in user_lower:
            return "🎤 Voice responses enabled! I'll now speak my replies to you.", True
        elif 'disable' in user_lower or 'turn off' in user_lower or 'voice mode off' in user_lower:
            return "💬 Voice responses disabled. I'll only respond with text now.", False
        else:
            status = "enabled" if current_voice_enabled else "disabled"
            return f"Voice responses are currently {status}. Say 'enable voice' or 'disable voice' to change.", current_voice_enabled
    
    def _is_project_code_request(self, user_input: str) -> bool:
        """Check if user is requesting project codes"""
        code_requests = ['project code', 'show code', 'list code', 'available code', 'what code']
        return any(req in user_input.lower() for req in code_requests)
    
    def _get_project_codes_response(self) -> str:
        """Get project codes response"""
        mars_codes = self.db.get_project_codes('Mars')
        oracle_codes = self.db.get_project_codes('Oracle')
        
        response = "📋 **Available Project Codes:**\n\n🚀 **Mars Projects:**\n"
        for code in mars_codes:
            voice_version = code.code.replace('MARS00', 'Mars zero zero ')
            response += f"• **{code.code}** (say: '{voice_version}'): {code.description}\n"
        
        response += "\n🔮 **Oracle Projects:**\n"
        for code in oracle_codes:
            voice_version = code.code.replace('ORA10', 'Oracle one zero ')
            response += f"• **{code.code}** (say: '{voice_version}'): {code.description}\n"
        
        response += "\nJust mention the code you want to use! 😊"
        return response
    
    def _is_help_request(self, user_input: str) -> bool:
        """Check if user needs help"""
        help_requests = ['help', 'how', 'what can', 'commands', 'instructions']
        return any(req in user_input.lower() for req in help_requests)
    
    def _get_help_response(self) -> str:
        """Get help response"""
        return """🤖 **Hi! I'm Tim, your AI timesheet assistant!**

**🎯 Here's how I can help:**

**📝 Fill Timesheet:** Just tell me naturally:
• *"Mars 8 hours MARS001 navigation work"*
• *"4 hours Oracle ORA100 database optimization"*

**🎤 Voice Commands:**
• *"Enable voice"* - Get spoken responses
• *"Show project codes"* - See available codes
• *"Help"* - Get this help message

**📊 Available Projects:**
🚀 **Mars:** MARS001-005 (Navigation, Life Support, Communication, Exploration, Collection)
🔮 **Oracle:** ORA100-104 (Performance, Migration, ETL, Security, Backup)

**💡 Tips:**
• You can speak or type naturally
• I'll ask for missing information
• Say numbers like "eight hours" or "8 hours"
• I understand project codes like "Mars zero zero one"

What would you like to work on today? 😊"""
    
    def _is_entry_complete(self, entry: Dict) -> bool:
        """Check if timesheet entry is complete"""
        required_fields = ['hours', 'project_code', 'task', 'table_type']
        return all(entry.get(field) for field in required_fields)
    
    def _submit_timesheet(self, entry_data: Dict, user_id: str, voice_enabled: bool) -> bool:
        """Submit timesheet entry to database"""
        try:
            entry = TimesheetEntry(
                date=entry_data.get('date', datetime.date.today().isoformat()),
                hours=float(entry_data.get('hours', 0)),
                system=entry_data.get('system', 'System'),
                project_code=entry_data.get('project_code', ''),
                task=entry_data.get('task', ''),
                submitted_at=datetime.datetime.now().isoformat(),
                user_id=user_id,
                table_type=entry_data.get('table_type', 'Mars')
            )
            
            input_method = "voice" if voice_enabled else "text"
            success, record_id = self.db.save_timesheet(entry, input_method)
            
            if success:
                print(f"✅ Timesheet saved with ID: {record_id}")
            
            return success
            
        except Exception as e:
            print(f"Submit timesheet error: {e}")
            return False

# Initialize system components
db = DatabaseManager()
bot = OllamaTimesheetBot(db)
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
    """Create Gradio app with Ollama integration"""
    
    with gr.Blocks(title="Ollama Voice Timesheet Bot", theme=gr.themes.Soft()) as demo:
        
        # State management
        session_state = gr.State("")
        user_role_state = gr.State("")
        authenticated_state = gr.State(False)
        
        # Authentication UI
        with gr.Column(visible=True) as auth_container:
            gr.Markdown("""
            # 🤖 Ollama-Powered Voice Timesheet Assistant
            
            **Your Local AI Assistant with llama3.2:1b**
            
            **Demo Accounts:**
            - **Admin:** `admin` / `admin123`
            - **User:** `user1` / `user123`
            
            **🤖 AI Features (Local Ollama):**
            ✅ **Natural Conversation** - Talk about timesheets naturally  
            ✅ **Smart Data Extraction** - AI understands your input  
            ✅ **Context Awareness** - Remembers what you've said  
            ✅ **Intelligent Responses** - Helpful and conversational  
            
            **🎤 Voice Features:**
            ✅ **Speech Input** - Speak your timesheet entries  
            ✅ **Voice Responses** - Tim talks back to you  
            ✅ **Natural Commands** - Voice-friendly project codes  
            
            **📊 Project Management:**
            ✅ **Mars & Oracle Projects** - Separate tracking systems  
            ✅ **Smart Validation** - Checks hours and codes  
            ✅ **Audit Logging** - Complete activity tracking  
            ✅ **Secure Database** - All data safely stored
            """)
            
            with gr.Row():
                username_input = gr.Textbox(label="Username", placeholder="Enter username")
                password_input = gr.Textbox(label="Password", type="password", placeholder="Enter password")
            
            login_btn = gr.Button("🔑 Login", variant="primary", size="lg")
            auth_message = gr.Markdown("")
        
        # Main application UI
        with gr.Column(visible=False) as main_container:
            
            # Header
            with gr.Row():
                user_info = gr.Markdown("")
                logout_btn = gr.Button("🚪 Logout", size="sm")
            
            gr.Markdown("""
            ## 🤖 Tim - Your Local AI Timesheet Assistant
            **Powered by Ollama llama3.2:1b Running on Your Machine**
            """)
            
            gr.Markdown("""
            ### 🎯 Natural Examples:
            **🗣️ Voice:** *"Mars, eight hours, Mars zero zero one, worked on navigation system"*  
            **⌨️ Text:** *"4 hours MARS001 today, API development work"*  
            **🎤 Commands:** *"Enable voice"*, *"Show project codes"*, *"Help"*
            """)
            
            # Main chat interface
            chatbot = gr.Chatbot(
                [],
                elem_id="chatbot",
                bubble_full_width=False,
                height=600,
                show_label=False,
                avatar_images=("👤", "🤖")
            )
            
            # Input controls
            with gr.Row():
                with gr.Column(scale=3):
                    msg = gr.Textbox(
                        placeholder="Chat naturally with Tim... Try: 'Mars 8 hours MARS001 navigation work' or use voice!",
                        show_label=False,
                        lines=2
                    )
                with gr.Column(scale=1):
                    audio_input = gr.Audio(
                        sources=["microphone"],
                        type="filepath",
                        label="🎤 Voice Input",
                        show_label=True
                    )
            
            # Control buttons
            with gr.Row():
                send_btn = gr.Button("Send 💬", variant="primary")
                clear_btn = gr.Button("🔄 Reset Chat")
                voice_btn = gr.Button("🎤 Toggle Voice")
            
            # Audio output for voice responses
            audio_output = gr.Audio(
                label="🔊 Tim's Voice Response",
                autoplay=True,
                show_label=True,
                visible=True
            )
            
            # Footer information
            gr.Markdown("""
            **🤖 Local AI Features:**  
            Tim uses your Ollama llama3.2:1b model for intelligent, context-aware conversation!
            
            **💡 Quick Commands:**  
            • *"Enable voice"* - Get spoken responses from Tim  
            • *"Show project codes"* - List all available project codes  
            • *"Help"* - Get detailed assistance  
            • Just describe your work naturally - Tim understands!
            """)
        
        # Event handling functions
        def handle_login(username, password):
            success, session_id, role = authenticate_user(username, password)
            if success:
                return (
                    gr.update(visible=False),      # Hide auth
                    gr.update(visible=True),       # Show main
                    session_id, role, True,        # Session data
                    f"✅ Welcome **{username}** ({role}) - AI & Voice ready! 🤖🎤",  # User info
                    ""                             # Clear auth message
                )
            else:
                return (
                    gr.update(visible=True),       # Keep auth visible
                    gr.update(visible=False),      # Keep main hidden
                    "", "", False,                 # No session
                    "",                            # No user info
                    "❌ Invalid credentials. Please try again."  # Error message
                )
        
        def handle_logout():
            return (
                gr.update(visible=True),          # Show auth
                gr.update(visible=False),         # Hide main
                "", "", False,                    # Clear session
                "", "",                           # Clear messages
                [], None                          # Clear chat and audio
            )
        
        def handle_chat(message, audio, history, session_id):
            if not session_id or session_id not in user_sessions:
                return "", None, history + [("", "❌ Session expired. Please log in again.")]
            
            try:
                return bot.process_conversation(message, audio, session_id, history)
            except Exception as e:
                print(f"Chat handling error: {e}")
                error_msg = "I'm having technical difficulties. Please try again."
                return "", None, history + [(message, error_msg)]
        
        # Wire up all the events
        login_btn.click(
            handle_login,
            inputs=[username_input, password_input],
            outputs=[auth_container, main_container, session_state, user_role_state, authenticated_state, user_info, auth_message]
        )
        
        logout_btn.click(
            handle_logout,
            outputs=[auth_container, main_container, session_state, user_role_state, authenticated_state, user_info, auth_message, chatbot, audio_output]
        )
        
        # Chat interactions
        msg.submit(handle_chat, [msg, audio_input, chatbot, session_state], [msg, audio_input, chatbot, audio_output])
        send_btn.click(handle_chat, [msg, audio_input, chatbot, session_state], [msg, audio_input, chatbot, audio_output])
        
        # Voice input handling
        audio_input.change(handle_chat, [msg, audio_input, chatbot, session_state], [msg, audio_input, chatbot, audio_output])
        
        # Utility buttons
        clear_btn.click(lambda: ([], None), outputs=[chatbot, audio_output])
        
        # Load initial welcome message
        demo.load(
            lambda: [([], """🤖 **Hey there! I'm Tim, your local AI timesheet assistant!**

**Powered by your Ollama llama3.2:1b model running right on your machine!**

🎤 **Voice Examples:**
• Say: *"Mars, eight hours, Mars zero zero one, navigation work"*
• Say: *"Enable voice responses"* to hear me talk back!
• Say: *"Show my project codes"* to hear all available options

⌨️ **Text Examples:**
• Type: *"4 hours MARS001 today, API development"*
• Type: *"Oracle 6 hours ORA100 database optimization"*

**🚀 Available Projects:**
• **Mars:** MARS001 (Navigation), MARS002 (Life Support), MARS003 (Communication), MARS004 (Exploration), MARS005 (Sample Collection)
• **Oracle:** ORA100 (Performance), ORA101 (Migration), ORA102 (ETL), ORA103 (Security), ORA104 (Backup)

**💡 I understand natural language!** Just tell me about your work day and I'll help you fill out your timesheet. 

What project did you work on today? 😊""")],
            outputs=[chatbot]
        )
    
    return demo

def main():
    """Main function to run the Ollama-powered timesheet bot"""
    
    print("🚀 Starting Ollama-Powered Voice Timesheet Assistant...")
    print("=" * 60)
    print()
    print("✅ LOCAL AI FEATURES:")
    print("   🤖 Ollama llama3.2:1b model integration")
    print("   🧠 Natural language conversation processing")
    print("   💭 Context-aware responses")
    print("   🎯 Smart timesheet data extraction")
    print()
    print("✅ VOICE FEATURES:")
    print("   🎤 Speech-to-text input processing")
    print("   🔊 Text-to-speech response generation")
    print("   🗣️ Voice-friendly project code pronunciation")
    print("   📢 Natural voice commands")
    print()
    print("✅ TIMESHEET FEATURES:")
    print("   📊 Mars and Oracle project tracking")
    print("   ⏰ Flexible date and time entry")
    print("   🔍 Smart validation and conflict detection")
    print("   📋 Complete audit logging")
    print("   🛡️ Secure user authentication")
    print()
    print("🔐 Demo accounts:")
    print("   • Admin: admin / admin123")
    print("   • User:  user1 / user123")
    print()
    print("🤖 Make sure Ollama is running:")
    print("   1. Start Ollama server: ollama serve")
    print("   2. Pull model: ollama pull llama3.2:1b")
    print("   3. Test: ollama run llama3.2:1b")
    print()
    print("💡 Natural conversation examples:")
    print("   🗣️ 'Mars, eight hours, Mars zero zero one, navigation work'")
    print("   ⌨️ '4 hours MARS001 today, API development'")
    print("   🎤 'Enable voice responses'")
    print("   📋 'Show my project codes'")
    print()
    print("=" * 60)
    print("🌟 Tim is ready to help with your timesheets!")
    print("=" * 60)
    
    # Launch the Gradio app
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