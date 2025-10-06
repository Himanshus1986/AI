
"""
Professional Conversational Timesheet Chatbot Backend API - Fixed Version
FastAPI with Advanced Field Validation, Confirmation Flow, and Pydantic v2 Compatibility
Fixed regex deprecation issue for modern Pydantic versions
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
    "temperature": 0.3,
    "num_ctx": 4096
}

# Fixed Pydantic Models with v2 compatibility
class ChatRequest(BaseModel):
    email: str = Field(..., min_length=5, pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')  # Fixed: regex -> pattern
    user_prompt: str = Field(..., min_length=1, max_length=2000)

class TimesheetEntryData(BaseModel):
    """Professional timesheet entry model with Pydantic v2 compatibility"""
    date: Optional[str] = Field(None, pattern=r'^\d{4}-\d{2}-\d{2}$')  # Fixed: regex -> pattern
    hours: Optional[float] = Field(None, ge=0.25, le=24.0)
    project_code: Optional[str] = Field(None, min_length=3, max_length=50)
    system: Optional[str] = Field(None, pattern=r'^(Oracle|Mars)$')  # Fixed: regex -> pattern
    task_code: Optional[str] = Field(None, max_length=50)
    comments: Optional[str] = Field(None, max_length=500)

class ConversationState(BaseModel):
    """Professional conversation state management"""
    user_email: str
    current_entry: TimesheetEntryData = TimesheetEntryData()
    conversation_phase: str = "input_gathering"
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

# Professional Database Manager
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

# Professional Natural Language Parser
class ProfessionalTimesheetParser:
    def __init__(self):
        self.model_name = OLLAMA_CONFIG["model_name"]
        self.temperature = OLLAMA_CONFIG["temperature"]
        self.num_ctx = OLLAMA_CONFIG["num_ctx"]

    def parse_timesheet_data(self, user_prompt: str) -> Dict[str, Any]:
        """Extract timesheet data with professional validation"""
        logger.info(f"Parsing user prompt: {user_prompt}")

        # Use deterministic parsing first, fallback to LLM if needed
        deterministic_data = self._deterministic_extract(user_prompt)

        # Enhance with LLM if needed
        if not deterministic_data or len(deterministic_data) < 2:
            llm_data = self._llm_extract(user_prompt)
            deterministic_data.update(llm_data)

        # Format and validate
        formatted_data = self._format_timesheet_data(deterministic_data)

        logger.info(f"Final parsed data: {formatted_data}")
        return formatted_data

    def _deterministic_extract(self, user_prompt: str) -> Dict[str, Any]:
        """Deterministic extraction without LLM hallucination"""
        data = {}
        prompt_lower = user_prompt.lower()

        # Extract system
        if re.search(r'\boracle\b', prompt_lower):
            data['system'] = 'Oracle'
        elif re.search(r'\bmars\b', prompt_lower):
            data['system'] = 'Mars'

        # Extract hours
        hours_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b', prompt_lower)
        if hours_match:
            data['hours'] = float(hours_match.group(1))

        # Extract project code
        project_match = re.search(r'\b([A-Z]{2,}-\d{3,})\b', user_prompt.upper())
        if project_match:
            data['project_code'] = project_match.group(1)

        # Extract date
        if re.search(r'\byesterday\b', prompt_lower):
            data['date'] = (date.today() - timedelta(days=1)).isoformat()
        elif re.search(r'\btoday\b', prompt_lower):
            data['date'] = date.today().isoformat()
        elif re.search(r'\btomorrow\b', prompt_lower):
            data['date'] = (date.today() + timedelta(days=1)).isoformat()

        # Extract date pattern
        date_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', user_prompt)
        if date_match:
            data['date'] = date_match.group(1)

        # Extract task code
        task_match = re.search(r'task\s*(?:code)?\s*:?\s*([A-Z0-9-]+)', user_prompt, re.IGNORECASE)
        if task_match:
            data['task_code'] = task_match.group(1)

        # Extract comments
        comment_patterns = [
            r'comment[s]?\s*:?\s*["']?([^"'\n]+)["']?',
            r'description\s*:?\s*["']?([^"'\n]+)["']?',
            r'worked\s+on\s+([^\n]+)',
            r'note[s]?\s*:?\s*["']?([^"'\n]+)["']?'
        ]

        for pattern in comment_patterns:
            comment_match = re.search(pattern, user_prompt, re.IGNORECASE)
            if comment_match:
                data['comments'] = comment_match.group(1).strip()
                break

        return data

    def _llm_extract(self, user_prompt: str) -> Dict[str, Any]:
        """Use LLM for enhanced extraction with strict validation"""
        try:
            extraction_prompt = f"""
Extract timesheet information from: "{user_prompt}"

Return ONLY a JSON object with fields found in the text. Do not guess or add information not explicitly stated.

Fields to look for:
- date: date in YYYY-MM-DD format or relative terms
- hours: numeric hours worked
- project_code: project identifier
- system: "Oracle" or "Mars"
- task_code: task identifier
- comments: work description

JSON only:
"""

            response = ollama.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": extraction_prompt}],
                options={"temperature": 0.1, "num_ctx": self.num_ctx}
            )

            response_text = response['message']['content'].strip()
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)

            if json_match:
                return json.loads(json_match.group(0))

        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")

        return {}

    def _format_timesheet_data(self, data: Dict) -> Dict[str, Any]:
        """Format and standardize timesheet data"""
        formatted = {}

        # Format date
        if 'date' in data and data['date']:
            formatted_date = self._parse_date(str(data['date']))
            if formatted_date:
                formatted['date'] = formatted_date

        # Format hours
        if 'hours' in data and data['hours'] is not None:
            try:
                hours_val = float(data['hours'])
                if 0.25 <= hours_val <= 24.0:
                    formatted['hours'] = round(hours_val, 2)
            except (ValueError, TypeError):
                pass

        # Format project code
        if 'project_code' in data and data['project_code']:
            formatted['project_code'] = str(data['project_code']).upper().strip()

        # Format system
        if 'system' in data and data['system']:
            system = str(data['system']).lower()
            if system in ['oracle', 'mars']:
                formatted['system'] = system.capitalize()

        # Format task code
        if 'task_code' in data and data['task_code']:
            formatted['task_code'] = str(data['task_code']).upper().strip()

        # Format comments
        if 'comments' in data and data['comments']:
            comments = str(data['comments']).strip()
            if len(comments) > 0:
                formatted['comments'] = comments[:500]  # Limit length

        return formatted

    def _parse_date(self, date_str: str) -> Optional[str]:
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

            # Return if already in correct format
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                return date_str

            # Try dateparser
            parsed = dateparser.parse(date_str)
            if parsed:
                return parsed.date().isoformat()

        except Exception as e:
            logger.warning(f"Date parsing failed for {date_str}: {e}")

        return None

# Session Management
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
            logger.warning(f"Session table initialization: {e}")

    def get_or_create_session(self, user_email: str) -> ConversationState:
        """Get existing session or create new one"""
        session_key = user_email.lower()

        if session_key in self.active_sessions:
            self.active_sessions[session_key].last_interaction = datetime.utcnow()
            return self.active_sessions[session_key]

        # Create new session
        new_session = ConversationState(user_email=user_email)
        self.active_sessions[session_key] = new_session
        return new_session

    def save_session(self, session: ConversationState):
        """Save session state"""
        session_key = session.user_email.lower()
        self.active_sessions[session_key] = session

# Timesheet Service
class TimesheetService:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self._initialize_timesheet_tables()

    def _initialize_timesheet_tables(self):
        """Initialize timesheet tables if they don't exist"""
        oracle_table = """
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='OracleTimesheet' AND xtype='U')
        CREATE TABLE OracleTimesheet (
            ID BIGINT IDENTITY(1,1) PRIMARY KEY,
            UserEmail NVARCHAR(255) NOT NULL,
            EntryDate DATE NOT NULL,
            ProjectCode NVARCHAR(50) NOT NULL,
            TaskCode NVARCHAR(50),
            Hours DECIMAL(5,2) NOT NULL,
            Comments NVARCHAR(500),
            Status NVARCHAR(20) DEFAULT 'Draft',
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
            Hours DECIMAL(5,2) NOT NULL,
            Comments NVARCHAR(500),
            Status NVARCHAR(20) DEFAULT 'Draft',
            CreatedAt DATETIME2 DEFAULT GETDATE(),
            UpdatedAt DATETIME2 DEFAULT GETDATE()
        )
        """

        try:
            self.db_manager.execute_query(oracle_table, fetch=False)
            self.db_manager.execute_query(mars_table, fetch=False)
        except Exception as e:
            logger.warning(f"Table initialization: {e}")

    def get_project_codes(self, system: str) -> List[Dict]:
        """Get valid project codes for system"""
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
        """Submit validated timesheet entry"""
        table_name = "OracleTimesheet" if system == "Oracle" else "MarsTimesheet"

        try:
            insert_query = f"""
            INSERT INTO {table_name} (UserEmail, EntryDate, ProjectCode, TaskCode, Hours, Comments, Status)
            VALUES (?, ?, ?, ?, ?, ?, 'Submitted')
            """

            rows_affected = self.db_manager.execute_query(
                insert_query,
                (user_email, entry.date, entry.project_code, entry.task_code, entry.hours, entry.comments),
                fetch=False
            )

            entry_id = f"{system}_{int(datetime.utcnow().timestamp())}"

            return {
                "success": True,
                "entry_id": entry_id,
                "system": system,
                "status": "Submitted",
                "rows_affected": rows_affected,
                "message": f"Successfully submitted timesheet entry to {system} system"
            }

        except Exception as e:
            logger.error(f"Failed to submit timesheet entry: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to submit timesheet entry to {system} system"
            }

# Conversational AI
class ConversationalAI:
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

        current_data = session.current_entry.dict(exclude_none=True)

        response = "I have the following information:\n"

        if current_data:
            for field, value in current_data.items():
                if value is not None:
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

        return response

    def _generate_confirmation_response(self, session: ConversationState) -> str:
        """Response while waiting for confirmation"""
        return "Please confirm if you want to submit this timesheet entry by saying 'YES' or 'NO'."

    def _generate_submission_response(self, session: ConversationState) -> str:
        """Response after successful submission"""
        return f"Your timesheet entry has been successfully submitted to the {session.current_entry.system} system!"

# Main Chatbot Controller
class ProfessionalChatbotController:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.session_manager = SessionManager(self.db_manager)
        self.parser = ProfessionalTimesheetParser()
        self.timesheet_service = TimesheetService(self.db_manager)
        self.conversational_ai = ConversationalAI()

        logger.info("Professional Chatbot Controller initialized")

    async def process_chat_message(self, chat_request: ChatRequest) -> ChatResponse:
        """Process chat message with professional validation"""
        try:
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
                response="I apologize, but I encountered an error. Please try again.",
                conversation_phase="error",
                missing_fields=[],
                session_id=f"session_{chat_request.email}_error"
            )

    async def _handle_confirmation(self, session: ConversationState, user_prompt: str) -> ChatResponse:
        """Handle confirmation phase interactions"""
        prompt_lower = user_prompt.lower().strip()

        # Check for confirmation
        if any(word in prompt_lower for word in ['yes', 'confirm', 'submit', 'ok', 'proceed']):
            result = self.timesheet_service.submit_timesheet_entry(
                session.current_entry, 
                session.user_email, 
                session.current_entry.system
            )

            if result["success"]:
                session.conversation_phase = "submitted"
                html_content = self._generate_submission_html(result, session.user_email)

                response = f"✅ **Success!** Your timesheet entry has been submitted to the {result['system']} system.\n\n"
                response += f"Entry ID: {result['entry_id']}\n"
                response += "Status: Submitted\n\n"
                response += "You can now enter another timesheet entry if needed."

                # Reset for new entry
                session.current_entry = TimesheetEntryData()
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

        else:
            return ChatResponse(
                response="I didn't understand. Please confirm by saying 'YES' to submit or 'NO' to cancel.",
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

    def _generate_html_content(self, session: ConversationState, missing_fields: List[str]) -> str:
        """Generate HTML content"""
        if session.conversation_phase == "input_gathering":
            return self._generate_data_collection_html(session, missing_fields)
        elif session.conversation_phase == "confirmation":
            return self._generate_confirmation_html(session)
        else:
            return ""

    def _generate_data_collection_html(self, session: ConversationState, missing_fields: List[str]) -> str:
        """Generate HTML for data collection"""
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
            background: #f8f9fa;
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
        """Generate HTML for confirmation"""
        entry = session.current_entry

        html = f"""
        <div class="timesheet-confirmation">
            <h3>✅ Ready to Submit - Please Confirm</h3>
            <table class="confirmation-table">
                <tbody>
                    <tr><td class="field-label">System:</td><td><strong>{entry.system}</strong></td></tr>
                    <tr><td class="field-label">Date:</td><td><strong>{entry.date}</strong></td></tr>
                    <tr><td class="field-label">Hours:</td><td><strong>{entry.hours}</strong></td></tr>
                    <tr><td class="field-label">Project Code:</td><td><strong>{entry.project_code}</strong></td></tr>
                    {f'<tr><td class="field-label">Task Code:</td><td><strong>{entry.task_code}</strong></td></tr>' if entry.task_code else ''}
                    {f'<tr><td class="field-label">Comments:</td><td><strong>{entry.comments}</strong></td></tr>' if entry.comments else ''}
                </tbody>
            </table>
            <p><strong>Please respond with 'YES' to confirm or 'NO' to cancel.</strong></p>
        </div>

        <style>
        .timesheet-confirmation {{
            margin: 20px 0;
            padding: 25px;
            border: 2px solid #28a745;
            border-radius: 10px;
            background: #d4edda;
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
        </style>
        """

        return html

    def _generate_submission_html(self, result: Dict, user_email: str) -> str:
        """Generate HTML for successful submission"""
        html = f"""
        <div class="submission-success">
            <h3>🎉 Timesheet Entry Successfully Submitted!</h3>
            <table class="success-table">
                <tbody>
                    <tr><td class="label">Entry ID:</td><td><strong>{result['entry_id']}</strong></td></tr>
                    <tr><td class="label">System:</td><td><strong>{result['system']}</strong></td></tr>
                    <tr><td class="label">Status:</td><td><strong>{result['status']}</strong></td></tr>
                    <tr><td class="label">User:</td><td><strong>{user_email}</strong></td></tr>
                    <tr><td class="label">Submitted At:</td><td><strong>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</strong></td></tr>
                </tbody>
            </table>
            <p>✅ Your timesheet entry has been successfully recorded.</p>
        </div>

        <style>
        .submission-success {{
            margin: 20px 0;
            padding: 25px;
            border: 2px solid #28a745;
            border-radius: 10px;
            background: #d4edda;
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
        </style>
        """

        return html

# FastAPI Application
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    logger.info("🚀 Starting Fixed Professional Timesheet Chatbot API...")

    try:
        # Test database connection
        db_manager = DatabaseManager()
        db_manager.execute_query("SELECT 1", fetch=True)
        logger.info("✅ Database connection successful")

        logger.info("🎯 Fixed API ready!")

    except Exception as e:
        logger.error(f"❌ Startup error: {e}")

    yield

    logger.info("🛑 Shutting down API...")

app = FastAPI(
    title="Fixed Professional Conversational Timesheet Chatbot API",
    description="Fixed Pydantic v2 compatibility issues - Expert-grade FastAPI backend",
    version="2.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize chatbot controller
chatbot_controller = ProfessionalChatbotController()

# API Endpoints
@app.get("/", tags=["General"])
async def root():
    """Root endpoint"""
    return {
        "message": "Fixed Professional Conversational Timesheet Chatbot API",
        "version": "2.1.0",
        "status": "operational",
        "fixed_issues": ["Pydantic v2 regex->pattern compatibility"],
        "features": [
            "Advanced field validation",
            "Confirmation workflow", 
            "Professional error handling"
        ]
    }

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    try:
        db_manager = DatabaseManager()
        db_manager.execute_query("SELECT 1", fetch=True)
        db_healthy = True
    except Exception as e:
        db_healthy = False

    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "database": "healthy" if db_healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.1.0"
    }

@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat_endpoint(chat_request: ChatRequest):
    """Main chat endpoint"""
    return await chatbot_controller.process_chat_message(chat_request)

@app.get("/projects/{system}", tags=["Projects"])
async def get_project_codes(system: str):
    """Get project codes for system"""
    if system not in ["Oracle", "Mars"]:
        raise HTTPException(status_code=400, detail="Invalid system")

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
        raise HTTPException(status_code=500, detail="Failed to retrieve project codes")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
