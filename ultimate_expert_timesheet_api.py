
"""
Ultimate Expert Conversational Timesheet API
Developed by a Master Timesheet Engineer with 50+ Years Experience

Features:
- Complete conversational flow with intelligent field validation
- Multi-system support (Oracle & Mars) with batch operations
- Professional confirmation workflow with draft management
- Advanced natural language processing with anti-hallucination
- Comprehensive API endpoints for all timesheet operations
- Tabular data formatting without HTML for direct consumption
- Intelligent user assistance and prompting
- Professional logging and database management
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
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
import uvicorn

# Professional logging with comprehensive tracking
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s'
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

# Ollama configuration for intelligent conversation
OLLAMA_CONFIG = {
    "model_name": "llama3.2:1b",
    "temperature": 0.2,  # Low temperature for consistent parsing
    "num_ctx": 4096
}

# Professional Pydantic Models
class ChatRequest(BaseModel):
    email: str = Field(..., min_length=5, pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    user_prompt: str = Field(..., min_length=1, max_length=2000)

class TimesheetEntry(BaseModel):
    """Complete timesheet entry with validation"""
    system: str = Field(..., pattern=r'^(Oracle|Mars)$')
    date: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    hours: float = Field(..., ge=0.25, le=24.0)
    project_code: str = Field(..., min_length=3, max_length=50)
    task_code: Optional[str] = Field(None, max_length=50)
    comments: Optional[str] = Field(None, max_length=500)

class DraftTimesheet(BaseModel):
    """Draft timesheet before confirmation"""
    user_email: str
    entries: List[Dict] = []
    total_hours: float = 0.0
    systems_used: List[str] = []
    status: str = "draft"
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ConversationState(BaseModel):
    """Advanced conversation state management"""
    user_email: str
    current_entries: List[Dict] = []
    conversation_phase: str = "gathering"  # gathering, confirmation, completed
    missing_fields: List[str] = []
    systems_in_progress: List[str] = []
    last_interaction: datetime = Field(default_factory=datetime.utcnow)
    draft_id: Optional[str] = None

class ChatResponse(BaseModel):
    """Enhanced response with tabular data"""
    response: str
    tabular_data: Optional[str] = None
    conversation_phase: str
    missing_fields: List[str] = []
    current_data: Optional[Dict] = None
    suggestions: List[str] = []
    session_id: str

class ProjectCodeResponse(BaseModel):
    """Project codes response"""
    system: str
    projects: List[Dict]
    count: int
    formatted_display: str

class TimesheetSummaryResponse(BaseModel):
    """Timesheet summary with formatted display"""
    user_email: str
    system: str
    entries: List[Dict]
    total_hours: float
    count: int
    formatted_display: str

# Ultimate Database Manager with Enterprise Features
class UltimateDatabaseManager:
    def __init__(self):
        self.connection_string = self._build_connection_string()
        self._init_connection_pool()
        self._initialize_all_tables()
        logger.info("Ultimate Database Manager initialized successfully")

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
                if query.strip().upper().startswith('INSERT') and 'OUTPUT INSERTED.ID' in query.upper():
                    result = cursor.fetchone()
                    return result[0] if result else None
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

    def _initialize_all_tables(self):
        """Initialize all required tables"""
        tables = {
            "OracleTimesheet": """
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
                UpdatedAt DATETIME2 DEFAULT GETDATE(),
                INDEX IX_OracleTimesheet_UserEmail_Date (UserEmail, EntryDate)
            )
            """,
            "MarsTimesheet": """
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
                UpdatedAt DATETIME2 DEFAULT GETDATE(),
                INDEX IX_MarsTimesheet_UserEmail_Date (UserEmail, EntryDate)
            )
            """,
            "ProjectCodes": """
            CREATE TABLE ProjectCodes (
                ID INT IDENTITY(1,1) PRIMARY KEY,
                ProjectCode NVARCHAR(50) NOT NULL,
                ProjectName NVARCHAR(255) NOT NULL,
                System NVARCHAR(20) NOT NULL CHECK (System IN ('Oracle', 'Mars', 'Both')),
                IsActive BIT DEFAULT 1,
                CreatedAt DATETIME2 DEFAULT GETDATE()
            )
            """,
            "ConversationSessions": """
            CREATE TABLE ConversationSessions (
                SessionID NVARCHAR(50) PRIMARY KEY,
                UserEmail NVARCHAR(255) NOT NULL,
                SessionData NVARCHAR(MAX),
                ConversationPhase NVARCHAR(50),
                LastInteraction DATETIME2 DEFAULT GETDATE(),
                CreatedAt DATETIME2 DEFAULT GETDATE(),
                INDEX IX_ConversationSessions_UserEmail (UserEmail)
            )
            """,
            "TimesheetDrafts": """
            CREATE TABLE TimesheetDrafts (
                DraftID NVARCHAR(50) PRIMARY KEY,
                UserEmail NVARCHAR(255) NOT NULL,
                DraftData NVARCHAR(MAX),
                TotalHours DECIMAL(8,2),
                SystemsUsed NVARCHAR(100),
                CreatedAt DATETIME2 DEFAULT GETDATE(),
                UpdatedAt DATETIME2 DEFAULT GETDATE(),
                INDEX IX_TimesheetDrafts_UserEmail (UserEmail)
            )
            """
        }

        for table_name, create_sql in tables.items():
            try:
                check_query = f"SELECT 1 FROM sysobjects WHERE name='{table_name}' AND xtype='U'"
                exists = self.execute_query(check_query)
                if not exists:
                    self.execute_query(create_sql, fetch=False)
                    logger.info(f"Created table: {table_name}")
            except Exception as e:
                logger.warning(f"Table {table_name} initialization: {e}")

        # Initialize sample project codes
        self._initialize_project_codes()

    def _initialize_project_codes(self):
        """Initialize sample project codes"""
        sample_projects = [
            ('ORG-001', 'Oracle Core Development', 'Oracle'),
            ('ORG-002', 'Oracle Database Maintenance', 'Oracle'),
            ('ORG-003', 'Oracle Integration Services', 'Oracle'),
            ('ORG-004', 'Oracle Security Implementation', 'Oracle'),
            ('ORG-005', 'Oracle Performance Optimization', 'Oracle'),
            ('MRS-001', 'Mars Data Processing', 'Mars'),
            ('MRS-002', 'Mars Analytics Platform', 'Mars'),
            ('MRS-003', 'Mars Reporting Services', 'Mars'),
            ('MRS-004', 'Mars Machine Learning', 'Mars'),
            ('MRS-005', 'Mars Data Visualization', 'Mars'),
            ('CMN-001', 'Common Documentation', 'Both'),
            ('CMN-002', 'Common Training', 'Both'),
            ('CMN-003', 'Common Testing', 'Both'),
            ('CMN-004', 'Common Architecture', 'Both'),
            ('CMN-005', 'Common Security', 'Both')
        ]

        try:
            check_query = "SELECT COUNT(*) FROM ProjectCodes"
            count = self.execute_query(check_query)[0][0]

            if count == 0:
                for code, name, system in sample_projects:
                    insert_query = """
                    INSERT INTO ProjectCodes (ProjectCode, ProjectName, System)
                    VALUES (?, ?, ?)
                    """
                    self.execute_query(insert_query, (code, name, system), fetch=False)
                logger.info("Initialized sample project codes")
        except Exception as e:
            logger.warning(f"Project codes initialization: {e}")

# Advanced Natural Language Parser
class ExpertTimesheetParser:
    def __init__(self):
        self.model_name = OLLAMA_CONFIG["model_name"]
        self.temperature = OLLAMA_CONFIG["temperature"]
        self.num_ctx = OLLAMA_CONFIG["num_ctx"]

    def parse_user_input(self, user_prompt: str) -> Dict[str, Any]:
        """Master parsing with multiple extraction methods"""
        logger.info(f"Expert parsing: {user_prompt}")

        # Method 1: Pattern-based extraction (most reliable)
        pattern_data = self._pattern_extract(user_prompt)

        # Method 2: LLM enhancement (when patterns insufficient)
        if len(pattern_data) < 2:
            llm_data = self._llm_extract(user_prompt)
            pattern_data.update(llm_data)

        # Method 3: Validation and formatting
        validated_data = self._validate_and_format(pattern_data, user_prompt)

        logger.info(f"Final parsed result: {validated_data}")
        return validated_data

    def _pattern_extract(self, prompt: str) -> Dict[str, Any]:
        """Expert pattern-based extraction"""
        data = {}
        prompt_lower = prompt.lower()

        # System extraction
        if re.search(r'\boracle\b', prompt_lower):
            data['system'] = 'Oracle'
        elif re.search(r'\bmars\b', prompt_lower):
            data['system'] = 'Mars'

        # Multi-system detection
        if re.search(r'\boracle\b.*\bmars\b|\bmars\b.*\boracle\b', prompt_lower):
            data['multi_system'] = True
            data['systems'] = ['Oracle', 'Mars']

        # Hours extraction with various formats
        hours_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b',
            r'worked\s+(\d+(?:\.\d+)?)(?:\s*hours?)?',
            r'(\d+(?:\.\d+)?)\s*(?:hrs?|h)\s+(?:on|for)'
        ]

        for pattern in hours_patterns:
            match = re.search(pattern, prompt_lower)
            if match:
                data['hours'] = float(match.group(1))
                break

        # Project code extraction
        project_patterns = [
            r'\b([A-Z]{2,4}-\d{3,4})\b',
            r'project\s*(?:code)?\s*:?\s*([A-Z0-9-]+)',
            r'on\s+([A-Z]{2,4}-\d{3,4})\b'
        ]

        for pattern in project_patterns:
            match = re.search(pattern, prompt.upper())
            if match:
                data['project_code'] = match.group(1)
                break

        # Date extraction
        date_keywords = {
            'yesterday': (date.today() - timedelta(days=1)).isoformat(),
            'today': date.today().isoformat(),
            'tomorrow': (date.today() + timedelta(days=1)).isoformat()
        }

        for keyword, date_value in date_keywords.items():
            if keyword in prompt_lower:
                data['date'] = date_value
                break

        # Specific date pattern
        date_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', prompt)
        if date_match:
            data['date'] = date_match.group(1)

        # Task code extraction
        task_patterns = [
            r'task\s*(?:code)?\s*:?\s*([A-Z0-9-]+)',
            r'activity\s*:?\s*([A-Z0-9-]+)'
        ]

        for pattern in task_patterns:
            match = re.search(pattern, prompt, re.IGNORECASE)
            if match:
                data['task_code'] = match.group(1).upper()
                break

        # Comments extraction
        comment_patterns = [
            r'comment[s]?\s*:?\s*["']?([^"'\n]+)["']?',
            r'description\s*:?\s*["']?([^"'\n]+)["']?',
            r'worked\s+on\s+([^\n,]+)',
            r'note[s]?\s*:?\s*["']?([^"'\n]+)["']?'
        ]

        for pattern in comment_patterns:
            match = re.search(pattern, prompt, re.IGNORECASE)
            if match:
                comment = match.group(1).strip()
                if len(comment) > 10:  # Only meaningful comments
                    data['comments'] = comment[:500]
                break

        return data

    def _llm_extract(self, prompt: str) -> Dict[str, Any]:
        """LLM extraction with strict validation"""
        try:
            extraction_prompt = f"""
Extract timesheet data from: "{prompt}"

Return JSON with ONLY explicitly mentioned fields:
- system: "Oracle" or "Mars" if mentioned
- date: YYYY-MM-DD format if date mentioned
- hours: number if hours mentioned
- project_code: code if project mentioned
- task_code: task if mentioned  
- comments: description if work details mentioned

JSON only, no explanation:
"""

            response = ollama.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": extraction_prompt}],
                options={"temperature": 0.1, "num_ctx": self.num_ctx}
            )

            json_match = re.search(r'\{.*\}', response['message']['content'], re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))

        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")

        return {}

    def _validate_and_format(self, data: Dict, original_prompt: str) -> Dict[str, Any]:
        """Expert validation and formatting"""
        validated = {}
        prompt_lower = original_prompt.lower()

        # Validate system
        if 'system' in data and data['system'] in ['Oracle', 'Mars']:
            validated['system'] = data['system']

        # Validate multi-system
        if 'multi_system' in data and data['multi_system']:
            validated['multi_system'] = True
            validated['systems'] = data.get('systems', [])

        # Validate hours
        if 'hours' in data:
            try:
                hours = float(data['hours'])
                if 0.25 <= hours <= 24.0:
                    validated['hours'] = round(hours, 2)
            except (ValueError, TypeError):
                pass

        # Validate project code
        if 'project_code' in data and data['project_code']:
            code = str(data['project_code']).upper().strip()
            if re.match(r'^[A-Z]{2,4}-\d{3,4}$', code):
                validated['project_code'] = code

        # Validate date
        if 'date' in data and data['date']:
            if re.match(r'^\d{4}-\d{2}-\d{2}$', data['date']):
                validated['date'] = data['date']

        # Validate task code
        if 'task_code' in data and data['task_code']:
            validated['task_code'] = str(data['task_code']).upper().strip()

        # Validate comments
        if 'comments' in data and data['comments']:
            comments = str(data['comments']).strip()
            if len(comments) >= 5:  # Meaningful comments only
                validated['comments'] = comments

        return validated

# Expert Session Manager
class ExpertSessionManager:
    def __init__(self, db_manager: UltimateDatabaseManager):
        self.db_manager = db_manager
        self.active_sessions: Dict[str, ConversationState] = {}

    def get_or_create_session(self, user_email: str) -> ConversationState:
        session_key = user_email.lower()

        if session_key in self.active_sessions:
            session = self.active_sessions[session_key]
            session.last_interaction = datetime.utcnow()
            return session

        # Load from database or create new
        try:
            query = """
            SELECT SessionData, ConversationPhase 
            FROM ConversationSessions 
            WHERE UserEmail = ? AND LastInteraction > ?
            ORDER BY LastInteraction DESC
            """
            cutoff = datetime.utcnow() - timedelta(hours=24)
            results = self.db_manager.execute_query(query, (user_email, cutoff))

            if results and results[0][0]:
                session_data = json.loads(results[0][0])
                session = ConversationState(**session_data)
                self.active_sessions[session_key] = session
                return session

        except Exception as e:
            logger.warning(f"Session load failed: {e}")

        # Create new session
        new_session = ConversationState(user_email=user_email)
        self.active_sessions[session_key] = new_session
        return new_session

    def save_session(self, session: ConversationState):
        try:
            session_data = session.dict()
            session_json = json.dumps(session_data, default=str)

            upsert_query = """
            MERGE ConversationSessions AS target
            USING (SELECT ? AS UserEmail) AS source
            ON target.UserEmail = source.UserEmail
            WHEN MATCHED THEN
                UPDATE SET SessionData = ?, ConversationPhase = ?, LastInteraction = GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (SessionID, UserEmail, SessionData, ConversationPhase, LastInteraction)
                VALUES (?, ?, ?, ?, GETDATE())
            """

            session_id = f"session_{session.user_email}_{int(datetime.utcnow().timestamp())}"
            self.db_manager.execute_query(
                upsert_query,
                (session.user_email, session_json, session.conversation_phase,
                 session_id, session.user_email, session_json, session.conversation_phase),
                fetch=False
            )

            # Update in-memory cache
            session_key = session.user_email.lower()
            self.active_sessions[session_key] = session

        except Exception as e:
            logger.error(f"Session save failed: {e}")

# Ultimate Timesheet Service
class UltimateTimesheetService:
    def __init__(self, db_manager: UltimateDatabaseManager):
        self.db_manager = db_manager

    def get_project_codes(self, system: Optional[str] = None) -> ProjectCodeResponse:
        """Get project codes with formatted display"""
        try:
            if system:
                query = """
                SELECT ProjectCode, ProjectName, System
                FROM ProjectCodes 
                WHERE (System = ? OR System = 'Both') AND IsActive = 1
                ORDER BY ProjectCode
                """
                results = self.db_manager.execute_query(query, (system,))
            else:
                query = """
                SELECT ProjectCode, ProjectName, System
                FROM ProjectCodes 
                WHERE IsActive = 1
                ORDER BY System, ProjectCode
                """
                results = self.db_manager.execute_query(query)

            projects = [
                {"code": row[0], "name": row[1], "system": row[2]}
                for row in results
            ]

            # Format for display
            if projects:
                display_lines = ["\n📋 **AVAILABLE PROJECT CODES**\n"]
                if system:
                    display_lines.append(f"System: **{system}**\n")

                display_lines.append("| Code | Project Name | System |")
                display_lines.append("|------|-------------|---------|")

                for project in projects:
                    display_lines.append(f"| **{project['code']}** | {project['name']} | {project['system']} |")

                display_lines.append(f"\n**Total: {len(projects)} projects available**")
                formatted_display = "\n".join(display_lines)
            else:
                formatted_display = "No project codes found."

            return ProjectCodeResponse(
                system=system or "All",
                projects=projects,
                count=len(projects),
                formatted_display=formatted_display
            )

        except Exception as e:
            logger.error(f"Failed to get project codes: {e}")
            return ProjectCodeResponse(
                system=system or "All",
                projects=[],
                count=0,
                formatted_display="Error retrieving project codes."
            )

    def get_user_timesheet(
        self, 
        user_email: str, 
        system: str, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None
    ) -> TimesheetSummaryResponse:
        """Get user timesheet with formatted display"""
        try:
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

            results = self.db_manager.execute_query(query, tuple(params))

            entries = []
            total_hours = 0.0

            for row in results:
                entry = {
                    "id": row[0],
                    "date": row[1].isoformat() if hasattr(row[1], 'isoformat') else str(row[1]),
                    "project_code": row[2],
                    "task_code": row[3] or "",
                    "hours": float(row[4]),
                    "comments": row[5] or "",
                    "status": row[6],
                    "created_at": row[7].isoformat() if hasattr(row[7], 'isoformat') else str(row[7])
                }
                entries.append(entry)
                total_hours += entry["hours"]

            # Format display
            if entries:
                display_lines = [f"\n📊 **{system.upper()} TIMESHEET SUMMARY**"]
                display_lines.append(f"User: **{user_email}**")
                if start_date or end_date:
                    date_range = f"From: {start_date or 'Beginning'} To: {end_date or 'End'}"
                    display_lines.append(f"Period: {date_range}")
                display_lines.append("")

                display_lines.append("| Date | Project | Task | Hours | Comments | Status |")
                display_lines.append("|------|---------|------|-------|----------|---------|")

                for entry in entries:
                    task = entry["task_code"] or "-"
                    comments = entry["comments"][:30] + "..." if len(entry["comments"]) > 30 else entry["comments"] or "-"
                    display_lines.append(
                        f"| {entry['date']} | **{entry['project_code']}** | {task} | "
                        f"**{entry['hours']}** | {comments} | {entry['status']} |"
                    )

                display_lines.append("")
                display_lines.append(f"**TOTAL HOURS: {total_hours}** | **ENTRIES: {len(entries)}**")
                formatted_display = "\n".join(display_lines)
            else:
                formatted_display = f"No timesheet entries found for {system} system."

            return TimesheetSummaryResponse(
                user_email=user_email,
                system=system,
                entries=entries,
                total_hours=total_hours,
                count=len(entries),
                formatted_display=formatted_display
            )

        except Exception as e:
            logger.error(f"Failed to get timesheet: {e}")
            return TimesheetSummaryResponse(
                user_email=user_email,
                system=system,
                entries=[],
                total_hours=0.0,
                count=0,
                formatted_display="Error retrieving timesheet data."
            )

    def save_draft_timesheet(self, user_email: str, entries: List[Dict]) -> Dict[str, Any]:
        """Save timesheet as draft"""
        try:
            draft_id = f"draft_{user_email}_{int(datetime.utcnow().timestamp())}"

            systems_used = list(set([entry.get('system') for entry in entries if entry.get('system')]))
            total_hours = sum([entry.get('hours', 0) for entry in entries])

            draft_data = {
                "entries": entries,
                "total_hours": total_hours,
                "systems_used": systems_used,
                "created_at": datetime.utcnow().isoformat()
            }

            insert_query = """
            INSERT INTO TimesheetDrafts (DraftID, UserEmail, DraftData, TotalHours, SystemsUsed)
            VALUES (?, ?, ?, ?, ?)
            """

            self.db_manager.execute_query(
                insert_query,
                (draft_id, user_email, json.dumps(draft_data), total_hours, ",".join(systems_used)),
                fetch=False
            )

            return {
                "success": True,
                "draft_id": draft_id,
                "total_hours": total_hours,
                "systems_used": systems_used,
                "entries_count": len(entries)
            }

        except Exception as e:
            logger.error(f"Failed to save draft: {e}")
            return {"success": False, "error": str(e)}

    def submit_timesheet_entries(self, user_email: str, entries: List[Dict]) -> Dict[str, Any]:
        """Submit multiple timesheet entries"""
        try:
            submitted_entries = []

            for entry in entries:
                system = entry['system']
                table_name = "OracleTimesheet" if system == "Oracle" else "MarsTimesheet"

                # Check for existing entry
                check_query = f"""
                SELECT ID FROM {table_name}
                WHERE UserEmail = ? AND EntryDate = ? AND ProjectCode = ?
                """
                existing = self.db_manager.execute_query(
                    check_query,
                    (user_email, entry['date'], entry['project_code'])
                )

                if existing:
                    # Update existing
                    update_query = f"""
                    UPDATE {table_name}
                    SET Hours = ?, TaskCode = ?, Comments = ?, Status = 'Submitted', UpdatedAt = GETDATE()
                    OUTPUT INSERTED.ID
                    WHERE ID = ?
                    """
                    entry_id = self.db_manager.execute_query(
                        update_query,
                        (entry['hours'], entry.get('task_code'), entry.get('comments'), existing[0][0])
                    )
                else:
                    # Insert new
                    insert_query = f"""
                    INSERT INTO {table_name} (UserEmail, EntryDate, ProjectCode, TaskCode, Hours, Comments, Status)
                    OUTPUT INSERTED.ID
                    VALUES (?, ?, ?, ?, ?, ?, 'Submitted')
                    """
                    entry_id = self.db_manager.execute_query(
                        insert_query,
                        (user_email, entry['date'], entry['project_code'], 
                         entry.get('task_code'), entry['hours'], entry.get('comments'))
                    )

                submitted_entries.append({
                    "id": entry_id,
                    "system": system,
                    "date": entry['date'],
                    "project_code": entry['project_code'],
                    "hours": entry['hours']
                })

            total_hours = sum([entry['hours'] for entry in entries])
            systems_used = list(set([entry['system'] for entry in entries]))

            return {
                "success": True,
                "entries_submitted": len(submitted_entries),
                "total_hours": total_hours,
                "systems_used": systems_used,
                "submitted_entries": submitted_entries
            }

        except Exception as e:
            logger.error(f"Failed to submit entries: {e}")
            return {"success": False, "error": str(e)}

    def delete_timesheet_entry(self, user_email: str, system: str, entry_id: int) -> Dict[str, Any]:
        """Delete a timesheet entry"""
        try:
            table_name = "OracleTimesheet" if system == "Oracle" else "MarsTimesheet"

            delete_query = f"""
            DELETE FROM {table_name}
            WHERE ID = ? AND UserEmail = ?
            """

            rows_affected = self.db_manager.execute_query(
                delete_query,
                (entry_id, user_email),
                fetch=False
            )

            if rows_affected > 0:
                return {"success": True, "message": f"Entry {entry_id} deleted from {system} system"}
            else:
                return {"success": False, "message": "Entry not found or access denied"}

        except Exception as e:
            logger.error(f"Failed to delete entry: {e}")
            return {"success": False, "error": str(e)}

# Master Conversational AI
class MasterConversationalAI:
    def __init__(self):
        self.model_name = OLLAMA_CONFIG["model_name"]
        self.temperature = 0.4
        self.num_ctx = OLLAMA_CONFIG["num_ctx"]

        # Expert system prompts
        self.system_prompts = {
            "master": """You are an EXPERT timesheet assistant with 50+ years of experience helping users manage their Oracle and Mars timesheets.

CORE PRINCIPLES:
1. Be conversational, helpful, and professional
2. NEVER hallucinate or guess information not provided
3. Ask for missing required fields one by one or accept multiple fields at once
4. Guide users through the complete timesheet process
5. Always confirm before submitting entries
6. Support both single and multi-system entries

REQUIRED FIELDS for timesheet entry:
- System: Oracle or Mars (or both)
- Date: YYYY-MM-DD format or relative (yesterday, today, etc.)
- Hours: Decimal hours worked (0.25 to 24.0)
- Project Code: Valid project code (e.g., ORG-001, MRS-002)
- Task Code: Optional task identifier
- Comments: Optional work description

CONVERSATION FLOW:
1. Gather required fields (ask for missing ones)
2. Show draft summary for confirmation
3. Submit after user confirms with YES/CONFIRM
4. Provide submission confirmation with details

AVAILABLE COMMANDS:
- "show projects [system]" - List available project codes
- "show timesheet [system]" - Display current timesheet entries  
- "help" - Show available commands
- "start fresh" - Begin new timesheet entry

Always be helpful and guide the user naturally through the process.""",

            "gathering": """Focus on collecting the missing timesheet information. Be conversational and helpful. 
Ask for one missing field at a time unless the user provides multiple fields together.""",

            "confirmation": """The user has provided all required information. Show a clear summary and ask for confirmation to submit.
User must respond with YES, CONFIRM, or similar to proceed. NO or CANCEL to abort.""",

            "completed": """Timesheet has been submitted. Congratulate the user and offer to help with additional entries."""
        }

    def generate_response(
        self, 
        session: ConversationState, 
        parsed_data: Dict, 
        missing_fields: List[str],
        context: str = ""
    ) -> str:
        """Generate expert conversational response"""

        prompt_type = session.conversation_phase
        system_prompt = self.system_prompts.get(prompt_type, self.system_prompts["master"])

        if session.conversation_phase == "gathering" and missing_fields:
            return self._generate_gathering_response(session, missing_fields, context)
        elif session.conversation_phase == "confirmation":
            return self._generate_confirmation_response(session, context)
        elif session.conversation_phase == "completed":
            return self._generate_completion_response(session, context)
        else:
            return self._generate_general_response(session, parsed_data, context)

    def _generate_gathering_response(self, session: ConversationState, missing_fields: List[str], context: str) -> str:
        """Generate response for data gathering phase"""
        current_data = [entry for entry in session.current_entries if entry]

        response_parts = []

        if current_data:
            response_parts.append("I have the following information so far:\n")
            for i, entry in enumerate(current_data, 1):
                response_parts.append(f"**Entry {i}:**")
                for field, value in entry.items():
                    if value is not None:
                        display_field = field.replace('_', ' ').title()
                        response_parts.append(f"  • {display_field}: **{value}**")
                response_parts.append("")

        if missing_fields:
            response_parts.append("I still need the following information:\n")

            field_questions = {
                'system': "Which system would you like to use? (Oracle or Mars, or both for multiple entries)",
                'date': "What date is this for? (e.g., 'yesterday', '2024-01-15', 'today')",
                'hours': "How many hours did you work? (e.g., '8 hours', '6.5 hrs')",
                'project_code': "What project code did you work on? (e.g., 'ORG-001', 'MRS-002')",
                'task_code': "What task or activity code? (optional - you can say 'none' to skip)",
                'comments': "Any comments about the work? (optional - you can say 'none' to skip)"
            }

            for field in missing_fields:
                question = field_questions.get(field, f"Please provide {field.replace('_', ' ')}")
                response_parts.append(f"• {question}")

        if context:
            response_parts.append(f"\n{context}")

        response_parts.append("\nYou can provide multiple fields at once or one at a time. Type 'show projects' to see available project codes.")

        return "\n".join(response_parts)

    def _generate_confirmation_response(self, session: ConversationState, context: str) -> str:
        """Generate confirmation prompt"""
        response_parts = ["✅ **READY TO SUBMIT** - Please confirm your timesheet entries:\n"]

        total_hours = 0
        systems_used = set()

        for i, entry in enumerate(session.current_entries, 1):
            response_parts.append(f"**Entry {i}:**")
            response_parts.append(f"  • System: **{entry.get('system')}**")
            response_parts.append(f"  • Date: **{entry.get('date')}**")
            response_parts.append(f"  • Hours: **{entry.get('hours')}**")
            response_parts.append(f"  • Project: **{entry.get('project_code')}**")

            if entry.get('task_code'):
                response_parts.append(f"  • Task: **{entry.get('task_code')}**")
            if entry.get('comments'):
                response_parts.append(f"  • Comments: **{entry.get('comments')}**")

            response_parts.append("")
            total_hours += entry.get('hours', 0)
            systems_used.add(entry.get('system'))

        response_parts.append(f"**SUMMARY:** {len(session.current_entries)} entries, {total_hours} total hours across {', '.join(systems_used)} system(s)")
        response_parts.append("\n**Please respond with:**")
        response_parts.append("• **'YES'** or **'CONFIRM'** to submit these entries")
        response_parts.append("• **'NO'** or **'CANCEL'** to cancel and start over")
        response_parts.append("• Or describe any changes you'd like to make")

        if context:
            response_parts.append(f"\n{context}")

        return "\n".join(response_parts)

    def _generate_completion_response(self, session: ConversationState, context: str) -> str:
        """Generate completion response"""
        response_parts = ["🎉 **SUCCESS!** Your timesheet entries have been submitted!"]

        if context:
            response_parts.append(f"\n{context}")

        response_parts.extend([
            "\n**Next steps:**",
            "• You can add more entries if needed",
            "• Type 'show timesheet [system]' to view your submitted entries",
            "• Type 'start fresh' to begin a new timesheet entry",
            "• Type 'help' for available commands"
        ])

        return "\n".join(response_parts)

    def _generate_general_response(self, session: ConversationState, parsed_data: Dict, context: str) -> str:
        """Generate general response"""
        response_parts = ["👋 Hello! I'm your expert timesheet assistant with 50+ years of experience."]
        response_parts.append("\nI can help you:")
        response_parts.append("• Fill out timesheets for Oracle and Mars systems")
        response_parts.append("• View your existing timesheet entries")
        response_parts.append("• Show available project codes")
        response_parts.append("• Handle multiple entries at once")

        response_parts.append("\n**To get started, you can:**")
        response_parts.append("• Tell me about your timesheet entry (e.g., '8 hours on Oracle project ORG-001 yesterday')")
        response_parts.append("• Ask to see project codes: 'show projects Oracle'")
        response_parts.append("• View your timesheet: 'show timesheet Mars'")
        response_parts.append("• Type 'help' for more commands")

        if context:
            response_parts.append(f"\n{context}")

        return "\n".join(response_parts)

# Ultimate Chatbot Controller
class UltimateChatbotController:
    def __init__(self):
        self.db_manager = UltimateDatabaseManager()
        self.session_manager = ExpertSessionManager(self.db_manager)
        self.parser = ExpertTimesheetParser()
        self.timesheet_service = UltimateTimesheetService(self.db_manager)
        self.conversational_ai = MasterConversationalAI()

        logger.info("Ultimate Chatbot Controller initialized - 50+ years expertise ready!")

    async def process_chat_message(self, chat_request: ChatRequest) -> ChatResponse:
        """Master chat processing with full conversation management"""
        try:
            session = self.session_manager.get_or_create_session(chat_request.email)
            user_prompt = chat_request.user_prompt.strip().lower()

            logger.info(f"Processing: {chat_request.email} -> {chat_request.user_prompt}")

            # Handle special commands
            if self._is_command(user_prompt):
                return await self._handle_command(session, chat_request.user_prompt)

            # Handle confirmation phase
            if session.conversation_phase == "confirmation":
                return await self._handle_confirmation(session, user_prompt)

            # Parse user input
            parsed_data = self.parser.parse_user_input(chat_request.user_prompt)

            # Update session with parsed data
            self._update_session_data(session, parsed_data)

            # Determine missing fields and conversation phase
            missing_fields = self._get_missing_fields(session)

            if not missing_fields and session.current_entries:
                session.conversation_phase = "confirmation"
            else:
                session.conversation_phase = "gathering"

            # Generate response
            ai_response = self.conversational_ai.generate_response(
                session, parsed_data, missing_fields
            )

            # Generate tabular data
            tabular_data = self._generate_tabular_data(session, missing_fields)

            # Generate suggestions
            suggestions = self._generate_suggestions(session, missing_fields)

            # Save session
            self.session_manager.save_session(session)

            return ChatResponse(
                response=ai_response,
                tabular_data=tabular_data,
                conversation_phase=session.conversation_phase,
                missing_fields=missing_fields,
                current_data={
                    "entries": session.current_entries,
                    "systems": session.systems_in_progress
                },
                suggestions=suggestions,
                session_id=f"session_{chat_request.email}"
            )

        except Exception as e:
            logger.error(f"Chat processing failed: {e}")
            return ChatResponse(
                response="I apologize, but I encountered an error. Please try again or type 'start fresh' to begin over.",
                tabular_data=None,
                conversation_phase="error",
                missing_fields=[],
                suggestions=["Try rephrasing your request", "Type 'help' for available commands"],
                session_id=f"session_{chat_request.email}_error"
            )

    def _is_command(self, prompt: str) -> bool:
        """Check if input is a special command"""
        commands = [
            'show projects', 'show timesheet', 'help', 'start fresh',
            'clear', 'reset', 'projects', 'timesheet'
        ]
        return any(cmd in prompt for cmd in commands)

    async def _handle_command(self, session: ConversationState, prompt: str) -> ChatResponse:
        """Handle special commands"""
        prompt_lower = prompt.lower().strip()

        if 'show projects' in prompt_lower or prompt_lower == 'projects':
            # Extract system if specified
            system = None
            if 'oracle' in prompt_lower:
                system = 'Oracle'
            elif 'mars' in prompt_lower:
                system = 'Mars'

            project_response = self.timesheet_service.get_project_codes(system)

            return ChatResponse(
                response=project_response.formatted_display,
                tabular_data=project_response.formatted_display,
                conversation_phase=session.conversation_phase,
                missing_fields=[],
                suggestions=[
                    "Use a project code in your timesheet entry",
                    "Type your timesheet details now"
                ],
                session_id=f"session_{session.user_email}"
            )

        elif 'show timesheet' in prompt_lower or prompt_lower == 'timesheet':
            # Extract system if specified
            system = 'Oracle'  # default
            if 'mars' in prompt_lower:
                system = 'Mars'
            elif 'oracle' in prompt_lower:
                system = 'Oracle'

            timesheet_response = self.timesheet_service.get_user_timesheet(
                session.user_email, system
            )

            return ChatResponse(
                response=timesheet_response.formatted_display,
                tabular_data=timesheet_response.formatted_display,
                conversation_phase=session.conversation_phase,
                missing_fields=[],
                suggestions=[
                    "Add a new timesheet entry",
                    f"Show {('Mars' if system == 'Oracle' else 'Oracle')} timesheet"
                ],
                session_id=f"session_{session.user_email}"
            )

        elif 'help' in prompt_lower:
            help_text = """
📚 **EXPERT TIMESHEET ASSISTANT - HELP**

**Available Commands:**
• `show projects [Oracle/Mars]` - View available project codes
• `show timesheet [Oracle/Mars]` - View your timesheet entries  
• `start fresh` or `clear` - Begin new timesheet entry
• `help` - Show this help message

**Timesheet Entry Examples:**
• "8 hours on Oracle project ORG-001 yesterday"
• "I worked 6.5 hours on Mars MRS-002 today, task DEV-123, database optimization"
• "Oracle: 4 hours ORG-003, Mars: 4 hours MRS-001, both yesterday"

**Required Information:**
• System: Oracle or Mars
• Date: yesterday, today, 2024-01-15, etc.
• Hours: 8, 6.5, etc.
• Project Code: ORG-001, MRS-002, etc.
• Task Code: (optional)
• Comments: (optional)

**Multi-System Support:**
You can book time in both Oracle and Mars systems in one conversation!

Just tell me what you worked on and I'll guide you through the process! 🚀
"""

            return ChatResponse(
                response=help_text,
                tabular_data=help_text,
                conversation_phase=session.conversation_phase,
                missing_fields=[],
                suggestions=[
                    "Try an example: '8 hours Oracle ORG-001 yesterday'",
                    "Show projects to see available codes"
                ],
                session_id=f"session_{session.user_email}"
            )

        elif 'start fresh' in prompt_lower or 'clear' in prompt_lower or 'reset' in prompt_lower:
            # Reset session
            session.current_entries = []
            session.conversation_phase = "gathering"
            session.missing_fields = []
            session.systems_in_progress = []

            self.session_manager.save_session(session)

            return ChatResponse(
                response="✨ **Fresh start!** I'm ready to help you with your timesheet entries.\n\nTell me what you worked on, or ask me to show available projects.",
                tabular_data=None,
                conversation_phase="gathering",
                missing_fields=[],
                suggestions=[
                    "Example: '8 hours Oracle ORG-001 yesterday'",
                    "Show projects Oracle",
                    "Help"
                ],
                session_id=f"session_{session.user_email}"
            )

        return ChatResponse(
            response="Command not recognized. Type 'help' for available commands.",
            tabular_data=None,
            conversation_phase=session.conversation_phase,
            missing_fields=[],
            suggestions=["help", "start fresh"],
            session_id=f"session_{session.user_email}"
        )

    async def _handle_confirmation(self, session: ConversationState, user_prompt: str) -> ChatResponse:
        """Handle confirmation phase"""
        if any(word in user_prompt for word in ['yes', 'confirm', 'submit', 'ok', 'proceed', 'y']):
            # Submit entries
            result = self.timesheet_service.submit_timesheet_entries(
                session.user_email, 
                session.current_entries
            )

            if result["success"]:
                # Format success response
                success_lines = [
                    "🎉 **TIMESHEET SUBMITTED SUCCESSFULLY!**\n",
                    f"**Entries Submitted:** {result['entries_submitted']}",
                    f"**Total Hours:** {result['total_hours']}",
                    f"**Systems Used:** {', '.join(result['systems_used'])}\n"
                ]

                success_lines.append("**Submitted Entries:**")
                success_lines.append("| System | Date | Project | Hours |")
                success_lines.append("|--------|------|---------|-------|")

                for entry in result['submitted_entries']:
                    success_lines.append(
                        f"| **{entry['system']}** | {entry['date']} | "
                        f"**{entry['project_code']}** | **{entry['hours']}** |"
                    )

                success_message = "\n".join(success_lines)

                # Reset session for new entries
                session.current_entries = []
                session.conversation_phase = "completed"
                session.missing_fields = []

                self.session_manager.save_session(session)

                return ChatResponse(
                    response=success_message,
                    tabular_data=success_message,
                    conversation_phase="completed",
                    missing_fields=[],
                    suggestions=[
                        "Add another timesheet entry",
                        "Show my timesheet",
                        "Start fresh"
                    ],
                    session_id=f"session_{session.user_email}"
                )
            else:
                return ChatResponse(
                    response=f"❌ **Error submitting timesheet:** {result.get('error', 'Unknown error')}\n\nPlease try again or contact support.",
                    tabular_data=None,
                    conversation_phase="confirmation",
                    missing_fields=[],
                    suggestions=["Try again", "Start fresh"],
                    session_id=f"session_{session.user_email}"
                )

        elif any(word in user_prompt for word in ['no', 'cancel', 'abort', 'n']):
            # Cancel submission
            session.current_entries = []
            session.conversation_phase = "gathering"
            session.missing_fields = []

            self.session_manager.save_session(session)

            return ChatResponse(
                response="❌ **Submission cancelled.** Let's start over.\n\nTell me about your timesheet entries.",
                tabular_data=None,
                conversation_phase="gathering",
                missing_fields=[],
                suggestions=[
                    "Example: '8 hours Oracle ORG-001 yesterday'",
                    "Show projects",
                    "Help"
                ],
                session_id=f"session_{session.user_email}"
            )

        else:
            # Try to parse as modification
            parsed_data = self.parser.parse_user_input(user_prompt)
            if parsed_data:
                # Update entries with modifications
                self._update_session_data(session, parsed_data)

                tabular_data = self._generate_tabular_data(session, [])

                return ChatResponse(
                    response="✏️ **Updated your entries.** Please review and confirm:\n\n" + 
                            self.conversational_ai.generate_response(session, parsed_data, [], ""),
                    tabular_data=tabular_data,
                    conversation_phase="confirmation",
                    missing_fields=[],
                    suggestions=["YES to confirm", "NO to cancel"],
                    session_id=f"session_{session.user_email}"
                )

            return ChatResponse(
                response="I didn't understand. Please respond with **'YES'** to submit or **'NO'** to cancel.",
                tabular_data=None,
                conversation_phase="confirmation",
                missing_fields=[],
                suggestions=["YES", "NO", "Cancel"],
                session_id=f"session_{session.user_email}"
            )

    def _update_session_data(self, session: ConversationState, parsed_data: Dict):
        """Update session with parsed data"""
        if not parsed_data:
            return

        # Handle multi-system entries
        if parsed_data.get('multi_system') and parsed_data.get('systems'):
            # Create entries for each system
            base_entry = {k: v for k, v in parsed_data.items() if k not in ['multi_system', 'systems']}

            for system in parsed_data['systems']:
                entry = base_entry.copy()
                entry['system'] = system

                # Check if we already have an entry for this system/date/project combination
                existing_idx = self._find_existing_entry(session, entry)
                if existing_idx is not None:
                    session.current_entries[existing_idx].update(entry)
                else:
                    session.current_entries.append(entry)

                if system not in session.systems_in_progress:
                    session.systems_in_progress.append(system)
        else:
            # Single entry update
            if len(session.current_entries) == 0:
                session.current_entries.append({})

            # Update the last entry or create new one if needed
            current_entry = session.current_entries[-1]

            for key, value in parsed_data.items():
                if key not in ['multi_system', 'systems'] and value is not None:
                    current_entry[key] = value

            # Track system
            if parsed_data.get('system') and parsed_data['system'] not in session.systems_in_progress:
                session.systems_in_progress.append(parsed_data['system'])

    def _find_existing_entry(self, session: ConversationState, entry: Dict) -> Optional[int]:
        """Find existing entry index that matches system/date/project"""
        for i, existing in enumerate(session.current_entries):
            if (existing.get('system') == entry.get('system') and
                existing.get('date') == entry.get('date') and
                existing.get('project_code') == entry.get('project_code')):
                return i
        return None

    def _get_missing_fields(self, session: ConversationState) -> List[str]:
        """Get missing required fields across all entries"""
        if not session.current_entries:
            return ['system', 'date', 'hours', 'project_code']

        required_fields = ['system', 'date', 'hours', 'project_code']
        missing = []

        for entry in session.current_entries:
            entry_missing = []
            for field in required_fields:
                if field not in entry or entry[field] is None or entry[field] == "":
                    entry_missing.append(field)

            # Add to overall missing if any entry is incomplete
            for field in entry_missing:
                if field not in missing:
                    missing.append(field)

        return missing

    def _generate_tabular_data(self, session: ConversationState, missing_fields: List[str]) -> Optional[str]:
        """Generate tabular representation of current data"""
        if not session.current_entries:
            return None

        if session.conversation_phase == "confirmation":
            # Generate confirmation table
            lines = ["\n**📋 TIMESHEET ENTRIES READY FOR SUBMISSION**\n"]
            lines.append("| # | System | Date | Project | Hours | Task | Comments |")
            lines.append("|---|---------|------|---------|-------|------|----------|")

            total_hours = 0
            for i, entry in enumerate(session.current_entries, 1):
                task = entry.get('task_code', '-')
                comments = entry.get('comments', '-')
                if comments and len(comments) > 20:
                    comments = comments[:17] + "..."

                lines.append(
                    f"| {i} | **{entry.get('system', '?')}** | {entry.get('date', '?')} | "
                    f"**{entry.get('project_code', '?')}** | **{entry.get('hours', '?')}** | "
                    f"{task} | {comments} |"
                )
                total_hours += entry.get('hours', 0)

            lines.append(f"\n**TOTAL HOURS: {total_hours}**")
            return "\n".join(lines)

        elif session.conversation_phase == "gathering":
            # Generate progress table
            lines = ["\n**📝 CURRENT PROGRESS**\n"]
            lines.append("| Field | Status | Value |")
            lines.append("|-------|--------|-------|")

            # Show progress for the current entry
            current_entry = session.current_entries[-1] if session.current_entries else {}

            fields_to_show = ['system', 'date', 'hours', 'project_code', 'task_code', 'comments']
            for field in fields_to_show:
                if field in current_entry and current_entry[field] is not None:
                    status = "✅"
                    value = f"**{current_entry[field]}**"
                elif field in ['task_code', 'comments']:
                    status = "⚪ Optional"
                    value = "Not specified"
                else:
                    status = "❌ Missing"
                    value = "Required"

                display_field = field.replace('_', ' ').title()
                lines.append(f"| {display_field} | {status} | {value} |")

            return "\n".join(lines)

        return None

    def _generate_suggestions(self, session: ConversationState, missing_fields: List[str]) -> List[str]:
        """Generate helpful suggestions for the user"""
        suggestions = []

        if session.conversation_phase == "gathering":
            if 'system' in missing_fields:
                suggestions.extend(["Oracle", "Mars", "Both Oracle and Mars"])
            elif 'project_code' in missing_fields:
                suggestions.extend(["Show projects Oracle", "Show projects Mars", "ORG-001", "MRS-002"])
            elif 'date' in missing_fields:
                suggestions.extend(["yesterday", "today", "2024-01-15"])
            elif 'hours' in missing_fields:
                suggestions.extend(["8 hours", "6.5 hours", "4 hours"])
            else:
                suggestions.extend(["Task code (optional)", "Comments (optional)", "Continue without optional fields"])

        elif session.conversation_phase == "confirmation":
            suggestions.extend(["YES - Submit entries", "NO - Cancel", "Make changes"])

        elif session.conversation_phase == "completed":
            suggestions.extend(["Add another entry", "Show my timesheet", "Start fresh", "Help"])

        else:
            suggestions.extend([
                "8 hours Oracle ORG-001 yesterday",
                "Show projects",
                "Show timesheet",
                "Help"
            ])

        return suggestions[:5]  # Limit to 5 suggestions

# FastAPI Application Setup
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    logger.info("🚀 Starting Ultimate Expert Timesheet API (50+ years experience)")

    try:
        # Test database connection
        db_manager = UltimateDatabaseManager()
        db_manager.execute_query("SELECT 1", fetch=True)
        logger.info("✅ Database connection successful")

        # Test Ollama (optional)
        try:
            models = ollama.list()
            logger.info(f"✅ Ollama available with {len(models.get('models', []))} models")
        except Exception as e:
            logger.warning(f"⚠️ Ollama not available: {e}")

        logger.info("🎯 Ultimate Timesheet API ready for expert-level service!")

    except Exception as e:
        logger.error(f"❌ Startup error: {e}")

    yield

    logger.info("🛑 Shutting down Ultimate Timesheet API")

app = FastAPI(
    title="Ultimate Expert Conversational Timesheet API",
    description="Master-level timesheet management with 50+ years of expertise. Supports conversational interactions, multi-system entries, intelligent validation, and comprehensive timesheet operations.",
    version="3.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the ultimate controller
ultimate_controller = UltimateChatbotController()

# Ultimate API Endpoints
@app.get("/", tags=["General"])
async def root():
    """Ultimate API root with comprehensive information"""
    return {
        "message": "Ultimate Expert Conversational Timesheet API",
        "version": "3.0.0",
        "expertise": "50+ Years Experience",
        "status": "operational",
        "features": [
            "Advanced conversational AI with natural language processing",
            "Multi-system support (Oracle & Mars)",
            "Intelligent field validation and anti-hallucination",
            "Professional confirmation workflow with draft management", 
            "Comprehensive project code management",
            "Tabular data formatting for direct consumption",
            "Expert user assistance and intelligent prompting",
            "Batch operations and multi-entry support",
            "Professional audit trail and logging",
            "Production-ready enterprise architecture"
        ],
        "systems_supported": ["Oracle", "Mars"],
        "operations": [
            "Fill timesheet entries",
            "View existing entries", 
            "Show project codes",
            "Update/delete entries",
            "Draft management",
            "Multi-system batch operations"
        ]
    }

@app.get("/health", tags=["Health"])
async def health_check():
    """Comprehensive health check"""
    try:
        db_manager = UltimateDatabaseManager()
        db_manager.execute_query("SELECT 1", fetch=True)
        db_healthy = True
        db_message = "Database connected and operational"
    except Exception as e:
        db_healthy = False
        db_message = f"Database error: {str(e)}"

    try:
        models = ollama.list()
        ollama_healthy = True
        ollama_message = f"Ollama operational with {len(models.get('models', []))} models"
    except Exception as e:
        ollama_healthy = False
        ollama_message = f"Ollama not available: {str(e)}"

    overall_status = "healthy" if db_healthy else "degraded"

    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "version": "3.0.0",
        "expertise_level": "50+ Years",
        "components": {
            "database": {
                "status": "healthy" if db_healthy else "unhealthy",
                "message": db_message
            },
            "ollama_llm": {
                "status": "healthy" if ollama_healthy else "degraded", 
                "message": ollama_message,
                "required": False
            },
            "conversational_ai": {
                "status": "healthy",
                "message": "Expert conversational AI ready"
            }
        },
        "capabilities": [
            "Natural language timesheet entry",
            "Multi-system support",
            "Intelligent validation",
            "Expert user assistance"
        ]
    }

@app.post("/chat", response_model=ChatResponse, tags=["Conversation"])
async def chat_endpoint(chat_request: ChatRequest):
    """Ultimate conversational chat endpoint with expert-level processing"""
    return await ultimate_controller.process_chat_message(chat_request)

@app.get("/projects", response_model=ProjectCodeResponse, tags=["Projects"])
@app.get("/projects/{system}", response_model=ProjectCodeResponse, tags=["Projects"])
async def get_project_codes(system: Optional[str] = None):
    """Get project codes with professional formatting"""
    if system and system not in ["Oracle", "Mars"]:
        raise HTTPException(
            status_code=400, 
            detail="Invalid system. Must be 'Oracle' or 'Mars'"
        )

    try:
        return ultimate_controller.timesheet_service.get_project_codes(system)
    except Exception as e:
        logger.error(f"Failed to get project codes: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to retrieve project codes"
        )

@app.get("/timesheet/{email}/{system}", response_model=TimesheetSummaryResponse, tags=["Timesheet"])
async def get_user_timesheet(
    email: str, 
    system: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
):
    """Get user timesheet with professional formatting"""
    if system not in ["Oracle", "Mars"]:
        raise HTTPException(
            status_code=400, 
            detail="Invalid system. Must be 'Oracle' or 'Mars'"
        )

    try:
        return ultimate_controller.timesheet_service.get_user_timesheet(
            email, system, start_date, end_date
        )
    except Exception as e:
        logger.error(f"Failed to get timesheet: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to retrieve timesheet entries"
        )

@app.post("/timesheet/submit", tags=["Timesheet"])
async def submit_timesheet_entries(entries: List[TimesheetEntry], user_email: str):
    """Submit multiple timesheet entries"""
    try:
        # Convert to dict format
        entry_dicts = []
        for entry in entries:
            entry_dicts.append({
                "system": entry.system,
                "date": entry.date,
                "hours": entry.hours,
                "project_code": entry.project_code,
                "task_code": entry.task_code,
                "comments": entry.comments
            })

        result = ultimate_controller.timesheet_service.submit_timesheet_entries(
            user_email, entry_dicts
        )

        if result["success"]:
            return {
                "message": "Timesheet entries submitted successfully",
                "entries_submitted": result["entries_submitted"],
                "total_hours": result["total_hours"],
                "systems_used": result["systems_used"]
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "Submission failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit entries: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to submit timesheet entries"
        )

@app.delete("/timesheet/{email}/{system}/{entry_id}", tags=["Timesheet"])
async def delete_timesheet_entry(email: str, system: str, entry_id: int):
    """Delete a specific timesheet entry"""
    if system not in ["Oracle", "Mars"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid system. Must be 'Oracle' or 'Mars'"
        )

    try:
        result = ultimate_controller.timesheet_service.delete_timesheet_entry(
            email, system, entry_id
        )

        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=404, detail=result["message"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete entry: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete timesheet entry"
        )

@app.post("/timesheet/draft", tags=["Timesheet"])
async def save_draft_timesheet(user_email: str, entries: List[Dict]):
    """Save timesheet entries as draft"""
    try:
        result = ultimate_controller.timesheet_service.save_draft_timesheet(
            user_email, entries
        )

        if result["success"]:
            return {
                "message": "Draft saved successfully",
                "draft_id": result["draft_id"],
                "total_hours": result["total_hours"],
                "systems_used": result["systems_used"]
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "Draft save failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save draft: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to save draft timesheet"
        )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
