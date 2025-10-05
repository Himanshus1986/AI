"""
Conversational Timesheet Chatbot Backend API
FastAPI application with SQL Server integration and Ollama LLM
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any, Union
from uuid import UUID, uuid4

import pyodbc
import dateparser
import ollama
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, DateTime, Boolean, Date, Numeric, Text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from contextlib import asynccontextmanager
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
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
    "temperature": 0.7,
    "num_ctx": 4096
}

# Pydantic Models
class ChatRequest(BaseModel):
    email: str
    user_prompt: str

class ChatResponse(BaseModel):
    response: str
    html_content: Optional[str] = None
    system_selected: Optional[str] = None
    session_id: Optional[str] = None

class TimesheetEntry(BaseModel):
    entry_date: date
    project_code: str
    task_code: Optional[str] = None
    hours: float
    description: Optional[str] = None

    @validator('hours')
    def validate_hours(cls, v):
        if v <= 0 or v > 24:
            raise ValueError('Hours must be between 0.01 and 24.00')
        return v

class UserContext(BaseModel):
    user_email: str
    selected_system: Optional[str] = None
    conversation_history: List[Dict] = []
    pending_entries: List[Dict] = []
    current_action: Optional[str] = None

# Database Models
Base = declarative_base()

class OracleTimesheet(Base):
    __tablename__ = "OracleTimesheet"

    ID = Column(Integer, primary_key=True)
    UserEmail = Column(String(255), nullable=False)
    EntryDate = Column(Date, nullable=False)
    ProjectCode = Column(String(50), nullable=False)
    TaskCode = Column(String(50))
    Hours = Column(Numeric(5,2), nullable=False)
    Description = Column(String(500))
    Status = Column(String(20), default='Draft')
    CreatedAt = Column(DateTime, default=datetime.utcnow)
    UpdatedAt = Column(DateTime, default=datetime.utcnow)

class MarsTimesheet(Base):
    __tablename__ = "MarsTimesheet"

    ID = Column(Integer, primary_key=True)
    UserEmail = Column(String(255), nullable=False)
    EntryDate = Column(Date, nullable=False)
    ProjectCode = Column(String(50), nullable=False)
    TaskCode = Column(String(50))
    Hours = Column(Numeric(5,2), nullable=False)
    Description = Column(String(500))
    Status = Column(String(20), default='Draft')
    CreatedAt = Column(DateTime, default=datetime.utcnow)
    UpdatedAt = Column(DateTime, default=datetime.utcnow)

class UserSession(Base):
    __tablename__ = "UserSessions"

    SessionID = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    UserEmail = Column(String(255), nullable=False)
    ConversationContext = Column(Text)
    SelectedSystem = Column(String(20))
    LastActivity = Column(DateTime, default=datetime.utcnow)
    CreatedAt = Column(DateTime, default=datetime.utcnow)

class ProjectCode(Base):
    __tablename__ = "ProjectCodes"

    ID = Column(Integer, primary_key=True)
    ProjectCode = Column(String(50), unique=True, nullable=False)
    ProjectName = Column(String(200), nullable=False)
    IsActive = Column(Boolean, default=True)
    System = Column(String(20), nullable=False)

# Database Connection
class DatabaseManager:
    def __init__(self):
        self.connection_string = self._build_connection_string()
        self.engine = create_engine(self.connection_string, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def _build_connection_string(self) -> str:
        """Build SQLAlchemy connection string for SQL Server"""
        return (
            f"mssql+pyodbc://{DATABASE_CONFIG['username']}:"
            f"{DATABASE_CONFIG['password']}@{DATABASE_CONFIG['server']}/"
            f"{DATABASE_CONFIG['database']}?driver={DATABASE_CONFIG['driver'].replace(' ', '+')}"
            f"&timeout={DATABASE_CONFIG['timeout']}"
        )

    def get_session(self) -> Session:
        """Get database session"""
        return self.SessionLocal()

    def close_session(self, session: Session):
        """Close database session"""
        session.close()

# Natural Language Processing
class DateTimeParser:
    @staticmethod
    def parse_date(date_string: str) -> Optional[date]:
        """Parse natural language date strings"""
        try:
            # Handle relative dates like "yesterday", "tomorrow", "last Monday"
            parsed_date = dateparser.parse(
                date_string,
                settings={
                    'PREFER_DAY_OF_MONTH': 'current',
                    'RETURN_AS_TIMEZONE_AWARE': False,
                    'DATE_ORDER': 'MDY'
                }
            )

            if parsed_date:
                return parsed_date.date()

            return None
        except Exception as e:
            logger.warning(f"Date parsing failed for '{date_string}': {e}")
            return None

    @staticmethod
    def parse_date_range(date_string: str) -> Optional[List[date]]:
        """Parse date ranges like 'this week', 'last week'"""
        try:
            today = date.today()

            if "this week" in date_string.lower():
                monday = today - timedelta(days=today.weekday())
                return [monday + timedelta(days=i) for i in range(5)]  # Mon-Fri

            elif "last week" in date_string.lower():
                last_monday = today - timedelta(days=today.weekday() + 7)
                return [last_monday + timedelta(days=i) for i in range(5)]  # Mon-Fri

            elif "next week" in date_string.lower():
                next_monday = today + timedelta(days=(7 - today.weekday()) % 7)
                return [next_monday + timedelta(days=i) for i in range(5)]  # Mon-Fri

            return None
        except Exception as e:
            logger.warning(f"Date range parsing failed for '{date_string}': {e}")
            return None

# Session Management
class SessionManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.in_memory_sessions: Dict[str, UserContext] = {}

    def get_or_create_session(self, user_email: str) -> UserContext:
        """Get existing session or create new one"""
        session_key = f"session_{user_email}"

        if session_key not in self.in_memory_sessions:
            # Try to load from database
            db_session = self.db_manager.get_session()
            try:
                user_session = db_session.query(UserSession).filter(
                    UserSession.UserEmail == user_email,
                    UserSession.LastActivity > datetime.utcnow() - timedelta(hours=24)
                ).first()

                if user_session and user_session.ConversationContext:
                    context_data = json.loads(user_session.ConversationContext)
                    self.in_memory_sessions[session_key] = UserContext(**context_data)
                else:
                    self.in_memory_sessions[session_key] = UserContext(user_email=user_email)

            except Exception as e:
                logger.warning(f"Failed to load session from DB: {e}")
                self.in_memory_sessions[session_key] = UserContext(user_email=user_email)
            finally:
                self.db_manager.close_session(db_session)

        return self.in_memory_sessions[session_key]

    def save_session(self, user_email: str, context: UserContext):
        """Save session to database and memory"""
        session_key = f"session_{user_email}"
        self.in_memory_sessions[session_key] = context

        # Save to database
        db_session = self.db_manager.get_session()
        try:
            user_session = db_session.query(UserSession).filter(
                UserSession.UserEmail == user_email
            ).first()

            context_json = context.json()

            if user_session:
                user_session.ConversationContext = context_json
                user_session.SelectedSystem = context.selected_system
                user_session.LastActivity = datetime.utcnow()
            else:
                user_session = UserSession(
                    UserEmail=user_email,
                    ConversationContext=context_json,
                    SelectedSystem=context.selected_system,
                    SessionID=str(uuid4())
                )
                db_session.add(user_session)

            db_session.commit()
        except Exception as e:
            logger.error(f"Failed to save session to DB: {e}")
            db_session.rollback()
        finally:
            self.db_manager.close_session(db_session)

# Ollama LLM Integration
class ConversationalAI:
    def __init__(self):
        self.model_name = OLLAMA_CONFIG["model_name"]
        self.temperature = OLLAMA_CONFIG["temperature"]
        self.num_ctx = OLLAMA_CONFIG["num_ctx"]

    def generate_response(self, messages: List[Dict[str, str]], context: UserContext) -> str:
        """Generate conversational response using Ollama"""
        try:
            # Build system prompt with context
            system_prompt = self._build_system_prompt(context)

            # Prepare messages for Ollama
            ollama_messages = [{"role": "system", "content": system_prompt}]
            ollama_messages.extend(messages[-5:])  # Keep last 5 messages for context

            # Call Ollama
            response = ollama.chat(
                model=self.model_name,
                messages=ollama_messages,
                options={
                    "temperature": self.temperature,
                    "num_ctx": self.num_ctx
                }
            )

            return response['message']['content']

        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            return "I apologize, but I'm having trouble processing your request right now. Please try again."

    def _build_system_prompt(self, context: UserContext) -> str:
        """Build system prompt with current context"""
        base_prompt = """
You are a helpful timesheet assistant chatbot. You help users fill out their timesheets for Oracle and Mars systems.

Key Guidelines:
1. Always be conversational and friendly
2. Ask clarifying questions when needed
3. Help parse natural language dates and times
4. Validate timesheet entries before saving
5. Provide clear feedback on actions taken
6. If user hasn't selected a system, ask them to choose between Oracle and Mars first

Available Commands:
- Fill timesheet for specific dates
- View existing timesheet entries
- Modify existing entries
- Copy previous week's timesheet
- Get available project codes
- Submit timesheet entries

Date Parsing Examples:
- "yesterday" = previous day
- "this week" = current Monday-Friday
- "last Monday" = previous Monday
- "2 hours on Mars project" = 2 hours entry

Always respond in a helpful, conversational manner.
"""

        if context.selected_system:
            base_prompt += f"\n\nCurrent System: {context.selected_system}"

        if context.pending_entries:
            base_prompt += f"\n\nPending Entries: {len(context.pending_entries)} entries waiting to be saved"

        return base_prompt

# Timesheet Business Logic
class TimesheetService:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.date_parser = DateTimeParser()

    def get_project_codes(self, system: str) -> List[Dict]:
        """Get available project codes for a system"""
        db_session = self.db_manager.get_session()
        try:
            projects = db_session.query(ProjectCode).filter(
                (ProjectCode.System == system) | (ProjectCode.System == 'Both'),
                ProjectCode.IsActive == True
            ).all()

            return [
                {
                    "code": p.ProjectCode,
                    "name": p.ProjectName,
                    "system": p.System
                }
                for p in projects
            ]
        finally:
            self.db_manager.close_session(db_session)

    def get_timesheet_entries(self, user_email: str, system: str, start_date: date = None, end_date: date = None) -> List[Dict]:
        """Get existing timesheet entries"""
        db_session = self.db_manager.get_session()
        try:
            # Select appropriate table
            table_class = OracleTimesheet if system == "Oracle" else MarsTimesheet

            query = db_session.query(table_class).filter(
                table_class.UserEmail == user_email
            )

            if start_date:
                query = query.filter(table_class.EntryDate >= start_date)
            if end_date:
                query = query.filter(table_class.EntryDate <= end_date)

            entries = query.all()

            return [
                {
                    "id": entry.ID,
                    "date": entry.EntryDate.isoformat(),
                    "project_code": entry.ProjectCode,
                    "task_code": entry.TaskCode,
                    "hours": float(entry.Hours),
                    "description": entry.Description,
                    "status": entry.Status
                }
                for entry in entries
            ]
        finally:
            self.db_manager.close_session(db_session)

    def save_timesheet_entries(self, user_email: str, system: str, entries: List[TimesheetEntry]) -> Dict[str, Any]:
        """Save timesheet entries to database"""
        db_session = self.db_manager.get_session()
        try:
            table_class = OracleTimesheet if system == "Oracle" else MarsTimesheet
            saved_entries = []

            for entry in entries:
                # Check if entry already exists
                existing = db_session.query(table_class).filter(
                    table_class.UserEmail == user_email,
                    table_class.EntryDate == entry.entry_date,
                    table_class.ProjectCode == entry.project_code
                ).first()

                if existing:
                    # Update existing entry
                    existing.Hours = entry.hours
                    existing.TaskCode = entry.task_code
                    existing.Description = entry.description
                    existing.UpdatedAt = datetime.utcnow()
                    saved_entries.append(existing.ID)
                else:
                    # Create new entry
                    new_entry = table_class(
                        UserEmail=user_email,
                        EntryDate=entry.entry_date,
                        ProjectCode=entry.project_code,
                        TaskCode=entry.task_code,
                        Hours=entry.hours,
                        Description=entry.description
                    )
                    db_session.add(new_entry)
                    db_session.flush()  # To get the ID
                    saved_entries.append(new_entry.ID)

            db_session.commit()
            return {
                "success": True,
                "entries_saved": len(saved_entries),
                "entry_ids": saved_entries
            }

        except Exception as e:
            db_session.rollback()
            logger.error(f"Failed to save timesheet entries: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            self.db_manager.close_session(db_session)

    def copy_previous_week_entries(self, user_email: str, system: str, target_week_start: date) -> Dict[str, Any]:
        """Copy previous week's entries to a new week"""
        previous_week_start = target_week_start - timedelta(days=7)
        previous_week_end = previous_week_start + timedelta(days=4)

        # Get previous week entries
        previous_entries = self.get_timesheet_entries(
            user_email, system, previous_week_start, previous_week_end
        )

        if not previous_entries:
            return {
                "success": False,
                "message": "No entries found for previous week"
            }

        # Convert to TimesheetEntry objects with new dates
        new_entries = []
        for i, entry in enumerate(previous_entries):
            new_date = target_week_start + timedelta(days=i % 5)  # Distribute across weekdays

            new_entries.append(TimesheetEntry(
                entry_date=new_date,
                project_code=entry["project_code"],
                task_code=entry["task_code"],
                hours=entry["hours"],
                description=entry["description"]
            ))

        # Save the copied entries
        return self.save_timesheet_entries(user_email, system, new_entries)

    def generate_timesheet_html(self, entries: List[Dict], title: str = "Timesheet Entries") -> str:
        """Generate HTML table for timesheet entries"""
        if not entries:
            return f"<div class='no-entries'><h3>{title}</h3><p>No timesheet entries found.</p></div>"

        html = f"""
        <div class="timesheet-container">
            <h3>{title}</h3>
            <table class="timesheet-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Project Code</th>
                        <th>Task Code</th>
                        <th>Hours</th>
                        <th>Description</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
        """

        total_hours = 0
        for entry in entries:
            total_hours += entry["hours"]
            html += f"""
                    <tr>
                        <td>{entry["date"]}</td>
                        <td>{entry["project_code"]}</td>
                        <td>{entry["task_code"] or '-'}</td>
                        <td>{entry["hours"]}</td>
                        <td>{entry["description"] or '-'}</td>
                        <td>{entry["status"]}</td>
                    </tr>
            """

        html += f"""
                </tbody>
                <tfoot>
                    <tr>
                        <td colspan="3"><strong>Total Hours:</strong></td>
                        <td><strong>{total_hours}</strong></td>
                        <td colspan="2"></td>
                    </tr>
                </tfoot>
            </table>
        </div>

        <style>
        .timesheet-container {{
            margin: 20px 0;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 8px;
            background-color: #f9f9f9;
        }}
        .timesheet-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        .timesheet-table th, .timesheet-table td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        .timesheet-table th {{
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
        }}
        .timesheet-table tr:nth-child(even) {{
            background-color: #f2f2f2;
        }}
        .timesheet-table tfoot td {{
            background-color: #e8f5e8;
            font-weight: bold;
        }}
        .no-entries {{
            text-align: center;
            color: #666;
            padding: 20px;
        }}
        </style>
        """

        return html

# Main Chatbot Controller
class ChatbotController:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.session_manager = SessionManager(self.db_manager)
        self.conversational_ai = ConversationalAI()
        self.timesheet_service = TimesheetService(self.db_manager)

    async def process_chat_message(self, chat_request: ChatRequest) -> ChatResponse:
        """Main method to process chat messages"""
        try:
            # Get or create user session
            user_context = self.session_manager.get_or_create_session(chat_request.email)

            # Add user message to conversation history
            user_context.conversation_history.append({
                "role": "user",
                "content": chat_request.user_prompt,
                "timestamp": datetime.utcnow().isoformat()
            })

            # Analyze user intent and extract information
            intent_analysis = await self._analyze_user_intent(chat_request.user_prompt, user_context)

            # Process the request based on intent
            response_data = await self._process_user_request(intent_analysis, user_context)

            # Generate conversational response
            ai_response = self._generate_ai_response(user_context, response_data)

            # Add AI response to conversation history
            user_context.conversation_history.append({
                "role": "assistant",
                "content": ai_response,
                "timestamp": datetime.utcnow().isoformat()
            })

            # Save session
            self.session_manager.save_session(chat_request.email, user_context)

            # Return response
            return ChatResponse(
                response=ai_response,
                html_content=response_data.get("html_content"),
                system_selected=user_context.selected_system,
                session_id=f"session_{chat_request.email}"
            )

        except Exception as e:
            logger.error(f"Chat processing failed: {e}")
            return ChatResponse(
                response="I apologize, but I encountered an error processing your request. Please try again.",
                html_content=None
            )

    async def _analyze_user_intent(self, user_prompt: str, context: UserContext) -> Dict[str, Any]:
        """Analyze user intent and extract structured information"""
        prompt_lower = user_prompt.lower()

        intent_analysis = {
            "intent": "general_chat",
            "system_selection": None,
            "dates": [],
            "project_codes": [],
            "hours": None,
            "action": None
        }

        # System selection
        if "oracle" in prompt_lower:
            intent_analysis["system_selection"] = "Oracle"
        elif "mars" in prompt_lower:
            intent_analysis["system_selection"] = "Mars"

        # Intent detection
        if any(word in prompt_lower for word in ["fill", "add", "enter", "timesheet", "hours"]):
            intent_analysis["intent"] = "fill_timesheet"
        elif any(word in prompt_lower for word in ["view", "show", "see", "display", "entries"]):
            intent_analysis["intent"] = "view_timesheet"
        elif any(word in prompt_lower for word in ["project", "codes", "available"]):
            intent_analysis["intent"] = "get_project_codes"
        elif any(word in prompt_lower for word in ["copy", "last week", "previous week"]):
            intent_analysis["intent"] = "copy_previous_week"
        elif any(word in prompt_lower for word in ["modify", "update", "change", "edit"]):
            intent_analysis["intent"] = "modify_timesheet"

        # Date extraction
        date_keywords = ["yesterday", "today", "tomorrow", "monday", "tuesday", "wednesday", 
                        "thursday", "friday", "this week", "last week", "next week"]

        for keyword in date_keywords:
            if keyword in prompt_lower:
                if "week" in keyword:
                    dates = self.timesheet_service.date_parser.parse_date_range(keyword)
                    if dates:
                        intent_analysis["dates"].extend(dates)
                else:
                    parsed_date = self.timesheet_service.date_parser.parse_date(keyword)
                    if parsed_date:
                        intent_analysis["dates"].append(parsed_date)

        # Hours extraction
        import re
        hours_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)', prompt_lower)
        if hours_match:
            intent_analysis["hours"] = float(hours_match.group(1))

        # Project code extraction
        project_matches = re.findall(r'([A-Z]{2,}-\d{3})', user_prompt.upper())
        if project_matches:
            intent_analysis["project_codes"] = project_matches

        return intent_analysis

    async def _process_user_request(self, intent_analysis: Dict[str, Any], context: UserContext) -> Dict[str, Any]:
        """Process user request based on intent analysis"""
        response_data = {"html_content": None, "message": ""}

        # Handle system selection
        if intent_analysis["system_selection"] and not context.selected_system:
            context.selected_system = intent_analysis["system_selection"]
            response_data["message"] = f"Great! I've set your system to {context.selected_system}. "

        # Check if system is selected for timesheet operations
        if intent_analysis["intent"] in ["fill_timesheet", "view_timesheet", "copy_previous_week"] and not context.selected_system:
            response_data["message"] = "Please first select which system you'd like to use: Oracle or Mars?"
            return response_data

        # Process different intents
        if intent_analysis["intent"] == "get_project_codes":
            if context.selected_system:
                projects = self.timesheet_service.get_project_codes(context.selected_system)
                project_html = self._generate_project_codes_html(projects)
                response_data["html_content"] = project_html
                response_data["message"] = f"Here are the available project codes for {context.selected_system}:"
            else:
                response_data["message"] = "Please select a system (Oracle or Mars) first to see project codes."

        elif intent_analysis["intent"] == "view_timesheet":
            start_date = min(intent_analysis["dates"]) if intent_analysis["dates"] else None
            end_date = max(intent_analysis["dates"]) if intent_analysis["dates"] else None

            entries = self.timesheet_service.get_timesheet_entries(
                context.user_email, 
                context.selected_system, 
                start_date, 
                end_date
            )

            if entries:
                response_data["html_content"] = self.timesheet_service.generate_timesheet_html(
                    entries, f"{context.selected_system} Timesheet Entries"
                )
                response_data["message"] = f"Here are your {context.selected_system} timesheet entries:"
            else:
                response_data["message"] = "No timesheet entries found for the specified period."

        elif intent_analysis["intent"] == "fill_timesheet":
            if intent_analysis["dates"] and intent_analysis["project_codes"] and intent_analysis["hours"]:
                # User provided complete information
                entries = []
                for entry_date in intent_analysis["dates"]:
                    for project_code in intent_analysis["project_codes"]:
                        entries.append(TimesheetEntry(
                            entry_date=entry_date,
                            project_code=project_code,
                            hours=intent_analysis["hours"],
                            description=f"Work on {project_code}"
                        ))

                result = self.timesheet_service.save_timesheet_entries(
                    context.user_email, 
                    context.selected_system, 
                    entries
                )

                if result["success"]:
                    response_data["message"] = f"Successfully saved {result['entries_saved']} timesheet entries!"
                    # Show saved entries
                    saved_entries = self.timesheet_service.get_timesheet_entries(
                        context.user_email, context.selected_system
                    )
                    if saved_entries:
                        response_data["html_content"] = self.timesheet_service.generate_timesheet_html(
                            saved_entries[-result['entries_saved']:], "Recently Saved Entries"
                        )
                else:
                    response_data["message"] = f"Failed to save entries: {result['error']}"
            else:
                # Ask for missing information
                missing = []
                if not intent_analysis["dates"]:
                    missing.append("date(s)")
                if not intent_analysis["project_codes"]:
                    missing.append("project code")
                if not intent_analysis["hours"]:
                    missing.append("hours")

                response_data["message"] = f"I need more information to fill your timesheet. Please provide: {', '.join(missing)}"

        elif intent_analysis["intent"] == "copy_previous_week":
            if intent_analysis["dates"]:
                target_date = intent_analysis["dates"][0]
                # Find Monday of the target week
                target_monday = target_date - timedelta(days=target_date.weekday())

                result = self.timesheet_service.copy_previous_week_entries(
                    context.user_email, 
                    context.selected_system, 
                    target_monday
                )

                if result["success"]:
                    response_data["message"] = f"Successfully copied previous week's entries! {result['entries_saved']} entries created."
                else:
                    response_data["message"] = result.get("message", "Failed to copy previous week's entries.")
            else:
                response_data["message"] = "Please specify which week you'd like to copy to (e.g., 'copy last week to this week')."

        return response_data

    def _generate_ai_response(self, context: UserContext, response_data: Dict[str, Any]) -> str:
        """Generate conversational AI response"""
        base_message = response_data.get("message", "")

        # Use Ollama to make the response more conversational
        try:
            messages = context.conversation_history[-3:] + [
                {"role": "assistant", "content": base_message}
            ]

            ai_response = self.conversational_ai.generate_response(messages, context)
            return ai_response if ai_response else base_message

        except Exception as e:
            logger.warning(f"AI response generation failed: {e}")
            return base_message or "How can I help you with your timesheet today?"

    def _generate_project_codes_html(self, projects: List[Dict]) -> str:
        """Generate HTML for project codes"""
        if not projects:
            return "<div class='no-projects'><p>No project codes found.</p></div>"

        html = """
        <div class="project-codes-container">
            <h3>Available Project Codes</h3>
            <table class="project-codes-table">
                <thead>
                    <tr>
                        <th>Code</th>
                        <th>Project Name</th>
                        <th>System</th>
                    </tr>
                </thead>
                <tbody>
        """

        for project in projects:
            html += f"""
                    <tr>
                        <td><strong>{project["code"]}</strong></td>
                        <td>{project["name"]}</td>
                        <td>{project["system"]}</td>
                    </tr>
            """

        html += """
                </tbody>
            </table>
        </div>

        <style>
        .project-codes-container {
            margin: 20px 0;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 8px;
            background-color: #f0f8ff;
        }
        .project-codes-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        .project-codes-table th, .project-codes-table td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        .project-codes-table th {
            background-color: #2196F3;
            color: white;
            font-weight: bold;
        }
        .project-codes-table tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        </style>
        """

        return html

# FastAPI Application
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Timesheet Chatbot API...")

    try:
        # Test Ollama connection
        models = ollama.list()
        logger.info(f"Ollama models available: {len(models.get('models', []))}")

        # Test database connection
        db_manager = DatabaseManager()
        session = db_manager.get_session()
        session.execute(text("SELECT 1"))
        db_manager.close_session(session)
        logger.info("Database connection successful")

    except Exception as e:
        logger.error(f"Startup error: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Timesheet Chatbot API...")

app = FastAPI(
    title="Conversational Timesheet Chatbot API",
    description="FastAPI backend for conversational timesheet management with Ollama LLM integration",
    version="1.0.0",
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
chatbot_controller = ChatbotController()

# API Endpoints
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Conversational Timesheet Chatbot API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database
        db_manager = DatabaseManager()
        session = db_manager.get_session()
        session.execute(text("SELECT 1"))
        db_manager.close_session(session)
        db_healthy = True
    except:
        db_healthy = False

    try:
        # Test Ollama
        models = ollama.list()
        ollama_healthy = True
    except:
        ollama_healthy = False

    return {
        "status": "healthy" if db_healthy and ollama_healthy else "unhealthy",
        "database": "healthy" if db_healthy else "unhealthy",
        "ollama": "healthy" if ollama_healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(chat_request: ChatRequest):
    """Main chat endpoint"""
    return await chatbot_controller.process_chat_message(chat_request)

@app.get("/projects/{system}")
async def get_project_codes(system: str):
    """Get project codes for a specific system"""
    if system not in ["Oracle", "Mars"]:
        raise HTTPException(status_code=400, detail="System must be 'Oracle' or 'Mars'")

    try:
        timesheet_service = TimesheetService(DatabaseManager())
        projects = timesheet_service.get_project_codes(system)
        return {"projects": projects}
    except Exception as e:
        logger.error(f"Failed to get project codes: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve project codes")

@app.get("/timesheet/{email}/{system}")
async def get_user_timesheet(email: str, system: str, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Get user timesheet entries"""
    if system not in ["Oracle", "Mars"]:
        raise HTTPException(status_code=400, detail="System must be 'Oracle' or 'Mars'")

    try:
        timesheet_service = TimesheetService(DatabaseManager())

        start_dt = datetime.fromisoformat(start_date).date() if start_date else None
        end_dt = datetime.fromisoformat(end_date).date() if end_date else None

        entries = timesheet_service.get_timesheet_entries(email, system, start_dt, end_dt)
        return {"entries": entries}
    except Exception as e:
        logger.error(f"Failed to get timesheet entries: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve timesheet entries")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
