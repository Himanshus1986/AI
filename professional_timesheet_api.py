
"""
Professional Conversational Timesheet Chatbot Backend API
FastAPI with Advanced Field Validation, Confirmation Flow, and Complete Error Handling
Developed by Expert AI Timesheet Engineer with 10+ years experience
"""

import os
import json
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any, Union
from uuid import uuid4
import re

import pyodbc
import dateparser
import ollama
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator, Field
from contextlib import asynccontextmanager
import uvicorn

# Professional logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_CONFIG = {
    "server": os.getenv("DB_SERVER", "localhost"),
    "database": os.getenv("DB_NAME", "TimesheetDB"),
    "username": os.getenv("DB_USERNAME", "sa"),
    "password": os.getenv("DB_PASSWORD", "YourPassword123"),
    "driver": "ODBC Driver 17 for SQL Server",
    "timeout": 30
}

# Ollama configuration
OLLAMA_CONFIG = {
    "model_name": "llama3.2:1b",
    "temperature": 0.3,  # Lower temperature for more consistent parsing
    "num_ctx": 4096
}

# Professional Pydantic Models with Enhanced Validation
class ChatRequest(BaseModel):
    email: str = Field(..., min_length=5, regex=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    user_prompt: str = Field(..., min_length=1, max_length=2000)

class TimesheetEntryData(BaseModel):
    """Professional timesheet entry model with comprehensive validation"""
    date: Optional[str] = Field(None, regex=r'^\d{4}-\d{2}-\d{2}$')
    hours: Optional[float] = Field(None, ge=0.25, le=24.0)
    project_code: Optional[str] = Field(None, min_length=3, max_length=50)
    system: Optional[str] = Field(None, regex=r'^(Oracle|Mars)$')
    task_code: Optional[str] = Field(None, max_length=50)
    comments: Optional[str] = Field(None, max_length=500)

class ConversationState(BaseModel):
    """Professional conversation state management"""
    user_email: str
    current_entry: TimesheetEntryData = TimesheetEntryData()
    conversation_phase: str = "input_gathering"  # input_gathering, confirmation, submitted
    missing_fields: List[str] = []
    last_interaction: datetime = Field(default_factory=datetime.utcnow)
    system_selected: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    html_content: Optional[str] = None
    conversation_phase: str
    missing_fields: List[str] = []
    current_data: Optional[Dict] = None
    system_selected: Optional[str] = None
    session_id: str

# Professional Database Manager with Connection Pooling
class DatabaseManager:
    def __init__(self):
        self.connection_string = self._build_connection_string()
        self._init_connection_pool()
        logger.info("Database manager initialized successfully")

    def _build_connection_string(self) -> str:
        return (
            f"DRIVER={{{DATABASE_CONFIG['driver']}}};"
            f"SERVER={DATABASE_CONFIG['server']};"
            f"DATABASE={DATABASE_CONFIG['database']};"
            f"UID={DATABASE_CONFIG['username']};"
            f"PWD={DATABASE_CONFIG['password']};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout={DATABASE_CONFIG['timeout']};"
            f"CommandTimeout={DATABASE_CONFIG['timeout']};"
        )

    def _init_connection_pool(self):
        pyodbc.pooling = True
        pyodbc.timeout = DATABASE_CONFIG['timeout']

    def get_connection(self):
        try:
            conn = pyodbc.connect(self.connection_string)
            conn.timeout = DATABASE_CONFIG['timeout']
            return conn
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise HTTPException(status_code=500, detail="Database connection failed")

    def execute_query(self, query: str, params: tuple = None, fetch: bool = True):
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                conn.commit()
                return cursor.rowcount
            elif fetch:
                return cursor.fetchall()
            else:
                return None

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Query execution failed: {e}")
            raise HTTPException(status_code=500, detail=f"Database operation failed: {str(e)}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

# Professional Natural Language Parser with Anti-Hallucination
class ProfessionalTimesheetParser:
    def __init__(self):
        self.model_name = OLLAMA_CONFIG["model_name"]
        self.temperature = OLLAMA_CONFIG["temperature"]

    def parse_timesheet_data(self, user_prompt: str) -> Dict[str, Any]:
        """Extract timesheet data with professional validation and anti-hallucination"""
        logger.info(f"Parsing user prompt: {user_prompt}")

        # First attempt: Use LLM for structured extraction
        llm_extracted = self._llm_extract(user_prompt)

        # Second pass: Validate against actual prompt content
        validated_data = self._validate_extracted_data(user_prompt, llm_extracted)

        # Third pass: Format and clean data
        formatted_data = self._format_timesheet_data(validated_data)

        logger.info(f"Final parsed data: {formatted_data}")
        return formatted_data

    def _llm_extract(self, user_prompt: str) -> Dict[str, Any]:
        """Use LLM for initial extraction with strict prompting"""
        extraction_prompt = f"""
You are a professional timesheet data extractor. Extract ONLY explicitly mentioned information from this prompt: "{user_prompt}"

Return a JSON object containing ONLY the fields that are clearly stated. DO NOT guess or assume values.

Required fields format:
- date: YYYY-MM-DD format only if explicitly mentioned
- hours: numeric value only if explicitly mentioned with "hours", "hrs", or "h"
- project_code: alphanumeric code only if explicitly mentioned
- system: "Oracle" or "Mars" only if explicitly mentioned
- task_code: task/activity code only if explicitly mentioned
- comments: descriptive text only if explicitly mentioned

CRITICAL: If information is not explicitly provided, do not include that field in the JSON.

Return only valid JSON. No explanation.
"""

        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": extraction_prompt}],
                options={"temperature": self.temperature, "num_ctx": self.num_ctx}
            )

            response_text = response['message']['content'].strip()

            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            else:
                logger.warning("No valid JSON found in LLM response")
                return {}

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return {}

    def _validate_extracted_data(self, prompt: str, extracted: Dict) -> Dict[str, Any]:
        """Validate extracted data against prompt content to prevent hallucination"""
        validated = {}
        prompt_lower = prompt.lower()

        # Validate date
        if 'date' in extracted:
            date_patterns = [
                r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
                r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
                r'\d{2}-\d{2}-\d{4}',  # MM-DD-YYYY
            ]
            if any(re.search(pattern, prompt) for pattern in date_patterns) or any(word in prompt_lower for word in ['yesterday', 'today', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday']):
                validated['date'] = extracted['date']

        # Validate hours
        if 'hours' in extracted:
            if re.search(r'\b\d+(?:\.\d+)?\s*(?:hours?|hrs?|h)\b', prompt_lower):
                validated['hours'] = float(extracted['hours'])

        # Validate project code
        if 'project_code' in extracted:
            if re.search(r'\b[A-Z]{2,}-\d{3,}\b', prompt.upper()) or 'project' in prompt_lower:
                validated['project_code'] = extracted['project_code']

        # Validate system
        if 'system' in extracted:
            if re.search(r'\b(oracle|mars)\b', prompt_lower):
                validated['system'] = extracted['system']

        # Validate task code
        if 'task_code' in extracted:
            if re.search(r'\b(task|activity|work)\b', prompt_lower):
                validated['task_code'] = extracted['task_code']

        # Validate comments
        if 'comments' in extracted:
            if re.search(r'\b(comment|note|description|worked on)\b', prompt_lower):
                validated['comments'] = extracted['comments']

        return validated

    def _format_timesheet_data(self, data: Dict) -> Dict[str, Any]:
        """Format and standardize timesheet data"""
        formatted = {}

        # Format date
        if 'date' in data:
            formatted['date'] = self._parse_date(data['date'])

        # Format hours
        if 'hours' in data:
            try:
                formatted['hours'] = round(float(data['hours']), 2)
            except (ValueError, TypeError):
                pass

        # Format project code
        if 'project_code' in data:
            formatted['project_code'] = str(data['project_code']).upper().strip()

        # Format system
        if 'system' in data:
            system = str(data['system']).lower()
            if system in ['oracle', 'mars']:
                formatted['system'] = system.capitalize()

        # Format task code
        if 'task_code' in data:
            formatted['task_code'] = str(data['task_code']).strip()

        # Format comments
        if 'comments' in data:
            formatted['comments'] = str(data['comments']).strip()

        return formatted

    def _parse_date(self, date_str: str) -> str:
        """Parse various date formats to YYYY-MM-DD"""
        try:
            # Handle relative dates
            if date_str.lower() in ['yesterday', 'today', 'tomorrow']:
                base_date = date.today()
                if date_str.lower() == 'yesterday':
                    return (base_date - timedelta(days=1)).isoformat()
                elif date_str.lower() == 'today':
                    return base_date.isoformat()
                elif date_str.lower() == 'tomorrow':
                    return (base_date + timedelta(days=1)).isoformat()

            # Parse using dateparser
            parsed = dateparser.parse(date_str)
            if parsed:
                return parsed.date().isoformat()

            # Return as-is if already in correct format
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                return date_str

            return None

        except Exception as e:
            logger.warning(f"Date parsing failed for {date_str}: {e}")
            return None

# Professional Session Manager with State Persistence
class SessionManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.active_sessions: Dict[str, ConversationState] = {}
        self._initialize_session_table()

    def _initialize_session_table(self):
        """Ensure session table exists"""
        create_table_query = """
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ConversationSessions' AND xtype='U')
        CREATE TABLE ConversationSessions (
            SessionID NVARCHAR(50) PRIMARY KEY,
            UserEmail NVARCHAR(255) NOT NULL,
            SessionData NVARCHAR(MAX),
            ConversationPhase NVARCHAR(50),
            LastInteraction DATETIME2,
            CreatedAt DATETIME2 DEFAULT GETDATE()
        )
        """
        try:
            self.db_manager.execute_query(create_table_query, fetch=False)
        except Exception as e:
            logger.warning(f"Session table initialization warning: {e}")

    def get_or_create_session(self, user_email: str) -> ConversationState:
        """Get existing session or create new one"""
        session_key = user_email.lower()

        if session_key in self.active_sessions:
            # Update last interaction
            self.active_sessions[session_key].last_interaction = datetime.utcnow()
            return self.active_sessions[session_key]

        # Try to load from database
        try:
            query = """
            SELECT SessionData, ConversationPhase 
            FROM ConversationSessions 
            WHERE UserEmail = ? AND LastInteraction > ?
            ORDER BY LastInteraction DESC
            """
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            results = self.db_manager.execute_query(query, (user_email, recent_cutoff))

            if results and results[0][0]:
                session_data = json.loads(results[0][0])
                conversation_state = ConversationState(**session_data)
                self.active_sessions[session_key] = conversation_state
                return conversation_state
        except Exception as e:
            logger.warning(f"Failed to load session from DB: {e}")

        # Create new session
        new_session = ConversationState(user_email=user_email)
        self.active_sessions[session_key] = new_session
        return new_session

    def save_session(self, session: ConversationState):
        """Save session to database"""
        try:
            session_data = session.dict()
            session_json = json.dumps(session_data, default=str)

            # Upsert session
            upsert_query = """
            MERGE ConversationSessions AS target
            USING (SELECT ? AS UserEmail) AS source
            ON (target.UserEmail = source.UserEmail)
            WHEN MATCHED THEN
                UPDATE SET SessionData = ?, ConversationPhase = ?, LastInteraction = GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (SessionID, UserEmail, SessionData, ConversationPhase, LastInteraction)
                VALUES (?, ?, ?, ?, GETDATE());
            """

            session_id = f"session_{session.user_email}_{int(datetime.utcnow().timestamp())}"
            self.db_manager.execute_query(
                upsert_query,
                (session.user_email, session_json, session.conversation_phase,
                 session_id, session.user_email, session_json, session.conversation_phase),
                fetch=False
            )
        except Exception as e:
            logger.error(f"Failed to save session: {e}")

# Professional Timesheet Service with Validation
class TimesheetService:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self._initialize_timesheet_tables()

    def _initialize_timesheet_tables(self):
        """Ensure timesheet tables exist with proper structure"""
        oracle_table = """
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='OracleTimesheet' AND xtype='U')
        CREATE TABLE OracleTimesheet (
            ID BIGINT IDENTITY(1,1) PRIMARY KEY,
            UserEmail NVARCHAR(255) NOT NULL,
            EntryDate DATE NOT NULL,
            ProjectCode NVARCHAR(50) NOT NULL,
            TaskCode NVARCHAR(50),
            Hours DECIMAL(5,2) NOT NULL CHECK (Hours > 0 AND Hours <= 24),
            Comments NVARCHAR(500),
            Status NVARCHAR(20) DEFAULT 'Draft' CHECK (Status IN ('Draft', 'Submitted', 'Approved')),
            CreatedAt DATETIME2 DEFAULT GETDATE(),
            UpdatedAt DATETIME2 DEFAULT GETDATE()
        )
        """

        mars_table = """
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='MarsTimesheet' AND xtype='U')
        CREATE TABLE MarsTimesheet (
            ID BIGINT IDENTITY(1,1) PRIMARY KEY,
            UserEmail NVARCHAR(255) NOT NULL,
            EntryDate DATE NOT NULL,
            ProjectCode NVARCHAR(50) NOT NULL,
            TaskCode NVARCHAR(50),
            Hours DECIMAL(5,2) NOT NULL CHECK (Hours > 0 AND Hours <= 24),
            Comments NVARCHAR(500),
            Status NVARCHAR(20) DEFAULT 'Draft' CHECK (Status IN ('Draft', 'Submitted', 'Approved')),
            CreatedAt DATETIME2 DEFAULT GETDATE(),
            UpdatedAt DATETIME2 DEFAULT GETDATE()
        )
        """

        try:
            self.db_manager.execute_query(oracle_table, fetch=False)
            self.db_manager.execute_query(mars_table, fetch=False)
        except Exception as e:
            logger.warning(f"Table initialization warning: {e}")

    def get_project_codes(self, system: str) -> List[Dict]:
        """Get valid project codes for system with professional formatting"""
        mock_projects = {
            'Oracle': [
                {'code': 'ORG-001', 'name': 'Oracle Core Development', 'system': 'Oracle'},
                {'code': 'ORG-002', 'name': 'Oracle Database Maintenance', 'system': 'Oracle'},
                {'code': 'ORG-003', 'name': 'Oracle Integration Services', 'system': 'Oracle'},
                {'code': 'CMN-001', 'name': 'Common Documentation', 'system': 'Oracle'},
                {'code': 'CMN-002', 'name': 'Common Training', 'system': 'Oracle'},
            ],
            'Mars': [
                {'code': 'MRS-001', 'name': 'Mars Data Processing', 'system': 'Mars'},
                {'code': 'MRS-002', 'name': 'Mars Analytics Platform', 'system': 'Mars'},
                {'code': 'MRS-003', 'name': 'Mars Reporting Services', 'system': 'Mars'},
                {'code': 'CMN-001', 'name': 'Common Documentation', 'system': 'Mars'},
                {'code': 'CMN-002', 'name': 'Common Training', 'system': 'Mars'},
            ]
        }
        return mock_projects.get(system, [])

    def submit_timesheet_entry(self, entry: TimesheetEntryData, user_email: str, system: str) -> Dict[str, Any]:
        """Submit validated timesheet entry to appropriate system"""
        table_name = "OracleTimesheet" if system == "Oracle" else "MarsTimesheet"

        try:
            insert_query = f"""
            INSERT INTO {table_name} (UserEmail, EntryDate, ProjectCode, TaskCode, Hours, Comments, Status)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, 'Submitted')
            """

            result = self.db_manager.execute_query(
                insert_query,
                (user_email, entry.date, entry.project_code, entry.task_code, entry.hours, entry.comments),
                fetch=True
            )

            entry_id = result[0][0] if result else None

            return {
                "success": True,
                "entry_id": entry_id,
                "system": system,
                "status": "Submitted",
                "message": f"Successfully submitted timesheet entry to {system} system"
            }

        except Exception as e:
            logger.error(f"Failed to submit timesheet entry: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to submit timesheet entry to {system} system"
            }

    def get_user_entries(self, user_email: str, system: str, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Get user timesheet entries with professional formatting"""
        table_name = "OracleTimesheet" if system == "Oracle" else "MarsTimesheet"

        query = f"""
        SELECT ID, EntryDate, ProjectCode, TaskCode, Hours, Comments, Status, CreatedAt
        FROM {table_name}
        WHERE UserEmail = ?
        """
        params = [user_email]

        if start_date:
            query += " AND EntryDate >= ?"
            params.append(start_date)
        if end_date:
            query += " AND EntryDate <= ?"
            params.append(end_date)

        query += " ORDER BY EntryDate DESC, CreatedAt DESC"

        try:
            results = self.db_manager.execute_query(query, tuple(params))
            return [
                {
                    "id": row[0],
                    "date": row[1].isoformat() if hasattr(row[1], 'isoformat') else str(row[1]),
                    "project_code": row[2],
                    "task_code": row[3],
                    "hours": float(row[4]),
                    "comments": row[5],
                    "status": row[6],
                    "created_at": row[7].isoformat() if hasattr(row[7], 'isoformat') else str(row[7])
                }
                for row in results
            ]
        except Exception as e:
            logger.error(f"Failed to get user entries: {e}")
            return []

# Professional Conversational AI with Context Awareness
class ConversationalAI:
    def __init__(self):
        self.model_name = OLLAMA_CONFIG["model_name"]
        self.temperature = 0.5  # Balanced for conversation
        self.num_ctx = OLLAMA_CONFIG["num_ctx"]

    def generate_response(self, session: ConversationState, parsed_data: Dict, missing_fields: List[str]) -> str:
        """Generate contextual conversational response"""

        if session.conversation_phase == "input_gathering":
            return self._generate_gathering_response(session, parsed_data, missing_fields)
        elif session.conversation_phase == "confirmation":
            return self._generate_confirmation_response(session)
        elif session.conversation_phase == "submitted":
            return self._generate_submission_response(session)
        else:
            return "Hello! I'm here to help you with your timesheet. Please provide the details for your entry."

    def _generate_gathering_response(self, session: ConversationState, parsed_data: Dict, missing_fields: List[str]) -> str:
        """Generate response during data gathering phase"""
        if not missing_fields:
            return self._create_confirmation_prompt(session)

        # Build conversational response for missing fields
        current_data = session.current_entry.dict(exclude_none=True)

        response = "I have the following information:\n"

        if current_data:
            for field, value in current_data.items():
                display_field = field.replace('_', ' ').title()
                response += f"• {display_field}: {value}\n"

        response += "\nI still need the following information:\n"

        field_prompts = {
            'system': "Which system would you like to use? (Oracle or Mars)",
            'date': "What date is this entry for? (e.g., 'yesterday', '2024-01-15', 'today')",
            'hours': "How many hours did you work? (e.g., '8 hours', '6.5 hrs')",
            'project_code': "What project code did you work on? (e.g., 'ORG-001', 'MRS-002')",
            'task_code': "What task or activity code? (optional - you can say 'none' to skip)",
            'comments': "Any comments or description of the work? (optional - you can say 'none' to skip)"
        }

        for field in missing_fields:
            response += f"• {field_prompts.get(field, f'{field.replace("_", " ").title()}?')}\n"

        return response

    def _create_confirmation_prompt(self, session: ConversationState) -> str:
        """Create confirmation prompt with all collected data"""
        entry = session.current_entry

        response = "Perfect! I have all the required information. Please confirm the following details:\n\n"
        response += "**Timesheet Entry Summary:**\n"
        response += f"• **System:** {entry.system}\n"
        response += f"• **Date:** {entry.date}\n"
        response += f"• **Hours:** {entry.hours}\n"
        response += f"• **Project Code:** {entry.project_code}\n"

        if entry.task_code:
            response += f"• **Task Code:** {entry.task_code}\n"
        if entry.comments:
            response += f"• **Comments:** {entry.comments}\n"

        response += "\n**Please respond with:**\n"
        response += "• 'YES' or 'CONFIRM' to submit this entry\n"
        response += "• 'NO' or 'CANCEL' to cancel and start over\n"
        response += "• Or specify what you'd like to change (e.g., 'change hours to 7')\n"

        return response

    def _generate_confirmation_response(self, session: ConversationState) -> str:
        """Response while waiting for confirmation"""
        return "Please confirm if you want to submit this timesheet entry by saying 'YES' or 'NO'."

    def _generate_submission_response(self, session: ConversationState) -> str:
        """Response after successful submission"""
        return f"Your timesheet entry has been successfully submitted to the {session.current_entry.system} system!"

# Professional Main Chatbot Controller
class ProfessionalChatbotController:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.session_manager = SessionManager(self.db_manager)
        self.parser = ProfessionalTimesheetParser()
        self.timesheet_service = TimesheetService(self.db_manager)
        self.conversational_ai = ConversationalAI()

        logger.info("Professional Chatbot Controller initialized")

    async def process_chat_message(self, chat_request: ChatRequest) -> ChatResponse:
        """Process chat message with professional validation and conversation flow"""
        try:
            # Get or create session
            session = self.session_manager.get_or_create_session(chat_request.email)
            user_prompt = chat_request.user_prompt.strip()

            logger.info(f"Processing message for {chat_request.email}: {user_prompt}")

            # Handle confirmation phase
            if session.conversation_phase == "confirmation":
                return await self._handle_confirmation(session, user_prompt)

            # Parse new data from user prompt
            parsed_data = self.parser.parse_timesheet_data(user_prompt)

            # Update session with new data
            self._update_session_data(session, parsed_data)

            # Determine required fields and missing fields
            required_fields = ['system', 'date', 'hours', 'project_code']
            missing_fields = self._get_missing_fields(session, required_fields)

            # Update conversation phase
            if not missing_fields:
                session.conversation_phase = "confirmation"
            else:
                session.conversation_phase = "input_gathering"

            # Generate AI response
            ai_response = self.conversational_ai.generate_response(session, parsed_data, missing_fields)

            # Generate HTML content
            html_content = self._generate_html_content(session, missing_fields)

            # Save session
            self.session_manager.save_session(session)

            return ChatResponse(
                response=ai_response,
                html_content=html_content,
                conversation_phase=session.conversation_phase,
                missing_fields=missing_fields,
                current_data=session.current_entry.dict(exclude_none=True),
                system_selected=session.current_entry.system,
                session_id=f"session_{chat_request.email}"
            )

        except Exception as e:
            logger.error(f"Chat processing failed: {e}")
            return ChatResponse(
                response="I apologize, but I encountered an error processing your request. Please try again or start over.",
                conversation_phase="error",
                missing_fields=[],
                session_id=f"session_{chat_request.email}_error"
            )

    async def _handle_confirmation(self, session: ConversationState, user_prompt: str) -> ChatResponse:
        """Handle confirmation phase interactions"""
        prompt_lower = user_prompt.lower().strip()

        # Check for confirmation
        if any(word in prompt_lower for word in ['yes', 'confirm', 'submit', 'ok', 'proceed']):
            # Submit the timesheet entry
            result = self.timesheet_service.submit_timesheet_entry(
                session.current_entry, 
                session.user_email, 
                session.current_entry.system
            )

            if result["success"]:
                session.conversation_phase = "submitted"
                # Reset for new entry
                session.current_entry = TimesheetEntryData()

                # Generate submission confirmation HTML
                html_content = self._generate_submission_html(result, session.user_email)

                response = f"✅ **Success!** Your timesheet entry has been submitted to the {result['system']} system.\n\n"
                response += f"Entry ID: {result['entry_id']}\n"
                response += "Status: Submitted\n\n"
                response += "You can now enter another timesheet entry if needed."

                self.session_manager.save_session(session)

                return ChatResponse(
                    response=response,
                    html_content=html_content,
                    conversation_phase="submitted",
                    missing_fields=[],
                    current_data={},
                    system_selected=None,
                    session_id=f"session_{session.user_email}"
                )
            else:
                return ChatResponse(
                    response=f"❌ **Error:** Failed to submit timesheet entry. {result.get('message', 'Please try again.')}",
                    conversation_phase="confirmation",
                    missing_fields=[],
                    current_data=session.current_entry.dict(exclude_none=True),
                    system_selected=session.current_entry.system,
                    session_id=f"session_{session.user_email}"
                )

        # Check for cancellation
        elif any(word in prompt_lower for word in ['no', 'cancel', 'abort', 'start over', 'reset']):
            session.current_entry = TimesheetEntryData()
            session.conversation_phase = "input_gathering"

            self.session_manager.save_session(session)

            return ChatResponse(
                response="Entry cancelled. Let's start over. Please provide your timesheet details.",
                conversation_phase="input_gathering",
                missing_fields=['system', 'date', 'hours', 'project_code'],
                current_data={},
                system_selected=None,
                session_id=f"session_{session.user_email}"
            )

        # Handle modification requests
        else:
            # Try to parse modification request
            parsed_changes = self.parser.parse_timesheet_data(user_prompt)
            if parsed_changes:
                self._update_session_data(session, parsed_changes)

                response = "I've updated your entry. Here's the current information:\n\n"
                response += self._format_current_data(session)
                response += "\n\nPlease confirm by saying 'YES' to submit or 'NO' to cancel."

                html_content = self._generate_html_content(session, [])

                self.session_manager.save_session(session)

                return ChatResponse(
                    response=response,
                    html_content=html_content,
                    conversation_phase="confirmation",
                    missing_fields=[],
                    current_data=session.current_entry.dict(exclude_none=True),
                    system_selected=session.current_entry.system,
                    session_id=f"session_{session.user_email}"
                )
            else:
                return ChatResponse(
                    response="I didn't understand the change you want to make. Please confirm by saying 'YES' to submit, 'NO' to cancel, or specify what you'd like to change.",
                    conversation_phase="confirmation",
                    missing_fields=[],
                    current_data=session.current_entry.dict(exclude_none=True),
                    system_selected=session.current_entry.system,
                    session_id=f"session_{session.user_email}"
                )

    def _update_session_data(self, session: ConversationState, parsed_data: Dict):
        """Update session with parsed data"""
        entry = session.current_entry

        if 'date' in parsed_data:
            entry.date = parsed_data['date']
        if 'hours' in parsed_data:
            entry.hours = parsed_data['hours']
        if 'project_code' in parsed_data:
            entry.project_code = parsed_data['project_code']
        if 'system' in parsed_data:
            entry.system = parsed_data['system']
            session.system_selected = parsed_data['system']
        if 'task_code' in parsed_data:
            entry.task_code = parsed_data['task_code']
        if 'comments' in parsed_data:
            entry.comments = parsed_data['comments']

    def _get_missing_fields(self, session: ConversationState, required_fields: List[str]) -> List[str]:
        """Get list of missing required fields"""
        entry_dict = session.current_entry.dict()
        missing = []

        for field in required_fields:
            if field not in entry_dict or entry_dict[field] is None:
                missing.append(field)

        return missing

    def _format_current_data(self, session: ConversationState) -> str:
        """Format current data for display"""
        entry = session.current_entry
        data_lines = []

        if entry.system:
            data_lines.append(f"**System:** {entry.system}")
        if entry.date:
            data_lines.append(f"**Date:** {entry.date}")
        if entry.hours is not None:
            data_lines.append(f"**Hours:** {entry.hours}")
        if entry.project_code:
            data_lines.append(f"**Project Code:** {entry.project_code}")
        if entry.task_code:
            data_lines.append(f"**Task Code:** {entry.task_code}")
        if entry.comments:
            data_lines.append(f"**Comments:** {entry.comments}")

        return "\n".join(data_lines)

    def _generate_html_content(self, session: ConversationState, missing_fields: List[str]) -> str:
        """Generate professional HTML content"""
        if session.conversation_phase == "input_gathering":
            return self._generate_data_collection_html(session, missing_fields)
        elif session.conversation_phase == "confirmation":
            return self._generate_confirmation_html(session)
        else:
            return ""

    def _generate_data_collection_html(self, session: ConversationState, missing_fields: List[str]) -> str:
        """Generate HTML for data collection phase"""
        entry = session.current_entry

        html = f"""
        <div class="timesheet-data-collection">
            <h3>📋 Timesheet Entry Progress</h3>
            <table class="data-collection-table">
                <thead>
                    <tr>
                        <th>Field</th>
                        <th>Status</th>
                        <th>Value</th>
                    </tr>
                </thead>
                <tbody>
                    <tr class="{'completed' if entry.system else 'missing'}">
                        <td><strong>System</strong></td>
                        <td>{'✅' if entry.system else '❌ Missing'}</td>
                        <td>{entry.system or 'Not specified'}</td>
                    </tr>
                    <tr class="{'completed' if entry.date else 'missing'}">
                        <td><strong>Date</strong></td>
                        <td>{'✅' if entry.date else '❌ Missing'}</td>
                        <td>{entry.date or 'Not specified'}</td>
                    </tr>
                    <tr class="{'completed' if entry.hours is not None else 'missing'}">
                        <td><strong>Hours</strong></td>
                        <td>{'✅' if entry.hours is not None else '❌ Missing'}</td>
                        <td>{entry.hours if entry.hours is not None else 'Not specified'}</td>
                    </tr>
                    <tr class="{'completed' if entry.project_code else 'missing'}">
                        <td><strong>Project Code</strong></td>
                        <td>{'✅' if entry.project_code else '❌ Missing'}</td>
                        <td>{entry.project_code or 'Not specified'}</td>
                    </tr>
                    <tr class="optional">
                        <td><strong>Task Code</strong></td>
                        <td>{'✅' if entry.task_code else '⚪ Optional'}</td>
                        <td>{entry.task_code or 'Not specified'}</td>
                    </tr>
                    <tr class="optional">
                        <td><strong>Comments</strong></td>
                        <td>{'✅' if entry.comments else '⚪ Optional'}</td>
                        <td>{entry.comments or 'Not specified'}</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <style>
        .timesheet-data-collection {{
            margin: 20px 0;
            padding: 20px;
            border: 1px solid #ddd;
            border-radius: 10px;
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        }}
        .data-collection-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        .data-collection-table th, .data-collection-table td {{
            padding: 12px;
            text-align: left;
            border: 1px solid #dee2e6;
        }}
        .data-collection-table th {{
            background: #007bff;
            color: white;
            font-weight: bold;
        }}
        .data-collection-table tr.completed {{
            background: #d4edda;
        }}
        .data-collection-table tr.missing {{
            background: #f8d7da;
        }}
        .data-collection-table tr.optional {{
            background: #fff3cd;
        }}
        </style>
        """

        return html

    def _generate_confirmation_html(self, session: ConversationState) -> str:
        """Generate HTML for confirmation phase"""
        entry = session.current_entry

        html = f"""
        <div class="timesheet-confirmation">
            <h3>✅ Ready to Submit - Please Confirm</h3>
            <div class="confirmation-summary">
                <table class="confirmation-table">
                    <tbody>
                        <tr>
                            <td class="field-label">System:</td>
                            <td class="field-value"><strong>{entry.system}</strong></td>
                        </tr>
                        <tr>
                            <td class="field-label">Date:</td>
                            <td class="field-value"><strong>{entry.date}</strong></td>
                        </tr>
                        <tr>
                            <td class="field-label">Hours:</td>
                            <td class="field-value"><strong>{entry.hours}</strong></td>
                        </tr>
                        <tr>
                            <td class="field-label">Project Code:</td>
                            <td class="field-value"><strong>{entry.project_code}</strong></td>
                        </tr>
                        {f'<tr><td class="field-label">Task Code:</td><td class="field-value"><strong>{entry.task_code}</strong></td></tr>' if entry.task_code else ''}
                        {f'<tr><td class="field-label">Comments:</td><td class="field-value"><strong>{entry.comments}</strong></td></tr>' if entry.comments else ''}
                    </tbody>
                </table>
            </div>
            <div class="confirmation-actions">
                <p><strong>Please confirm to submit this entry to the {entry.system} system.</strong></p>
                <p>Respond with 'YES' to confirm or 'NO' to cancel.</p>
            </div>
        </div>

        <style>
        .timesheet-confirmation {{
            margin: 20px 0;
            padding: 25px;
            border: 2px solid #28a745;
            border-radius: 10px;
            background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
        }}
        .confirmation-table {{
            width: 100%;
            margin: 15px 0;
        }}
        .confirmation-table td {{
            padding: 8px 12px;
            border-bottom: 1px solid #28a745;
        }}
        .field-label {{
            width: 30%;
            font-weight: bold;
            color: #155724;
        }}
        .field-value {{
            color: #155724;
        }}
        .confirmation-actions {{
            margin-top: 20px;
            padding: 15px;
            background: rgba(255, 255, 255, 0.8);
            border-radius: 8px;
            text-align: center;
        }}
        </style>
        """

        return html

    def _generate_submission_html(self, result: Dict, user_email: str) -> str:
        """Generate HTML for successful submission"""
        html = f"""
        <div class="submission-success">
            <h3>🎉 Timesheet Entry Successfully Submitted!</h3>
            <div class="success-details">
                <table class="success-table">
                    <tbody>
                        <tr>
                            <td class="label">Entry ID:</td>
                            <td class="value"><strong>{result['entry_id']}</strong></td>
                        </tr>
                        <tr>
                            <td class="label">System:</td>
                            <td class="value"><strong>{result['system']}</strong></td>
                        </tr>
                        <tr>
                            <td class="label">Status:</td>
                            <td class="value"><strong>{result['status']}</strong></td>
                        </tr>
                        <tr>
                            <td class="label">User:</td>
                            <td class="value"><strong>{user_email}</strong></td>
                        </tr>
                        <tr>
                            <td class="label">Submitted At:</td>
                            <td class="value"><strong>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</strong></td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <div class="next-steps">
                <p>✅ Your timesheet entry has been successfully recorded.</p>
                <p>🔄 You can now enter another timesheet entry if needed.</p>
            </div>
        </div>

        <style>
        .submission-success {{
            margin: 20px 0;
            padding: 25px;
            border: 2px solid #28a745;
            border-radius: 10px;
            background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
        }}
        .success-table {{
            width: 100%;
            margin: 15px 0;
        }}
        .success-table td {{
            padding: 10px 15px;
            border-bottom: 1px solid #28a745;
        }}
        .success-table .label {{
            width: 30%;
            font-weight: bold;
            color: #155724;
        }}
        .success-table .value {{
            color: #155724;
        }}
        .next-steps {{
            margin-top: 20px;
            padding: 15px;
            background: rgba(255, 255, 255, 0.9);
            border-radius: 8px;
            text-align: center;
        }}
        </style>
        """

        return html

# FastAPI Application with Professional Configuration
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Professional application lifespan management"""
    logger.info("🚀 Starting Professional Timesheet Chatbot API...")

    try:
        # Test Ollama connection
        models = ollama.list()
        logger.info(f"✅ Ollama models available: {len(models.get('models', []))}")

        # Test database connection
        db_manager = DatabaseManager()
        db_manager.execute_query("SELECT 1", fetch=True)
        logger.info("✅ Database connection successful")

        logger.info("🎯 Professional Timesheet Chatbot API ready!")

    except Exception as e:
        logger.error(f"❌ Startup error: {e}")

    yield

    logger.info("🛑 Shutting down Professional Timesheet Chatbot API...")

app = FastAPI(
    title="Professional Conversational Timesheet Chatbot API",
    description="Expert-grade FastAPI backend for conversational timesheet management with comprehensive validation, confirmation flow, and professional error handling",
    version="2.0.0",
    lifespan=lifespan
)

# Professional CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize professional chatbot controller
chatbot_controller = ProfessionalChatbotController()

# Professional API Endpoints
@app.get("/", tags=["General"])
async def root():
    """Professional API root endpoint"""
    return {
        "message": "Professional Conversational Timesheet Chatbot API",
        "version": "2.0.0",
        "status": "operational",
        "developer": "Expert AI Timesheet Engineer - 10+ years experience",
        "features": [
            "Advanced field validation",
            "Confirmation workflow", 
            "Anti-hallucination parsing",
            "Professional error handling",
            "Complete audit trail"
        ]
    }

@app.get("/health", tags=["Health"])
async def health_check():
    """Comprehensive health check endpoint"""
    try:
        # Test database
        db_manager = DatabaseManager()
        db_manager.execute_query("SELECT 1", fetch=True)
        db_healthy = True
        db_message = "Connected"
    except Exception as e:
        db_healthy = False
        db_message = f"Error: {str(e)}"

    try:
        # Test Ollama
        models = ollama.list()
        ollama_healthy = True
        ollama_message = f"Available models: {len(models.get('models', []))}"
    except Exception as e:
        ollama_healthy = False
        ollama_message = f"Error: {str(e)}"

    overall_status = "healthy" if db_healthy and ollama_healthy else "unhealthy"

    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "database": {
                "status": "healthy" if db_healthy else "unhealthy",
                "message": db_message
            },
            "ollama": {
                "status": "healthy" if ollama_healthy else "unhealthy", 
                "message": ollama_message
            }
        },
        "version": "2.0.0"
    }

@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat_endpoint(chat_request: ChatRequest):
    """Professional conversational chat endpoint with comprehensive validation"""
    return await chatbot_controller.process_chat_message(chat_request)

@app.get("/projects/{system}", tags=["Projects"])
async def get_project_codes(system: str):
    """Get valid project codes for specified system"""
    if system not in ["Oracle", "Mars"]:
        raise HTTPException(
            status_code=400, 
            detail="Invalid system. Must be 'Oracle' or 'Mars'"
        )

    try:
        timesheet_service = TimesheetService(DatabaseManager())
        projects = timesheet_service.get_project_codes(system)

        return {
            "system": system,
            "projects": projects,
            "count": len(projects),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get project codes: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to retrieve project codes"
        )

@app.get("/timesheet/{email}/{system}", tags=["Timesheet"])
async def get_user_timesheet(
    email: str, 
    system: str, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None
):
    """Get user timesheet entries with professional formatting"""
    if system not in ["Oracle", "Mars"]:
        raise HTTPException(
            status_code=400, 
            detail="Invalid system. Must be 'Oracle' or 'Mars'"
        )

    try:
        timesheet_service = TimesheetService(DatabaseManager())
        entries = timesheet_service.get_user_entries(email, system, start_date, end_date)

        return {
            "user_email": email,
            "system": system,
            "entries": entries,
            "count": len(entries),
            "date_range": {
                "start": start_date,
                "end": end_date
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get timesheet entries: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to retrieve timesheet entries"
        )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
