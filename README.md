# Conversational Timesheet Chatbot API Setup Guide

## Overview

This FastAPI-based conversational timesheet chatbot provides a complete backend for managing timesheets across Oracle and Mars systems using natural language processing with Ollama LLM integration.

## Features

✅ **Conversational Interface**: Natural language timesheet management  
✅ **Multi-System Support**: Oracle and Mars timesheet systems  
✅ **Natural Date Processing**: Supports "yesterday", "this week", "last Monday", etc.  
✅ **Session Management**: Maintains conversation context per user  
✅ **SQL Server Integration**: Full CRUD operations with validation  
✅ **Local LLM Integration**: Uses Ollama 3.2 1B model  
✅ **HTML Response Generation**: Ready-to-render timesheet tables  
✅ **Advanced Features**: Copy last week, modify entries, project code lookup  

## Prerequisites

### 1. Install Ollama
```bash
# Install Ollama (macOS/Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the required model
ollama pull llama3.2:1b
```

### 2. SQL Server Setup
- SQL Server 2019+ or SQL Server Express
- ODBC Driver 17 for SQL Server
- Create database named `TimesheetDB`

### 3. Python Environment
- Python 3.11+
- Virtual environment recommended

## Installation

### Option 1: Docker Setup (Recommended)

```bash
# Clone or create project directory
mkdir timesheet-chatbot && cd timesheet-chatbot

# Copy all provided files to the directory

# Create environment file
cp .env.template .env
# Edit .env with your configuration

# Start services
docker-compose up -d

# Check health
curl http://localhost:8000/health
```

### Option 2: Local Development Setup

```bash
# Create virtual environment
python -m venv timesheet-env
source timesheet-env/bin/activate  # Linux/Mac
# timesheet-env\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DB_SERVER=localhost
export DB_NAME=TimesheetDB
export DB_USERNAME=sa
export DB_PASSWORD=YourPassword123

# Run database setup
python -c "
import pyodbc
conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};'
    'SERVER=localhost;'
    'DATABASE=master;'
    'UID=sa;PWD=YourPassword123'
)
cursor = conn.cursor()
cursor.execute('CREATE DATABASE TimesheetDB')
conn.commit()
conn.close()
"

# Execute database schema
sqlcmd -S localhost -d TimesheetDB -i timesheet_database_schema.sql

# Start the API
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

### Main Chat Endpoint
```
POST /chat
Content-Type: application/json

{
    "email": "user@company.com",
    "user_prompt": "Fill 8 hours for Oracle project ORG-001 yesterday"
}
```

### Health Check
```
GET /health
```

### Get Project Codes
```
GET /projects/{system}  # system: Oracle or Mars
```

### Get Timesheet Entries
```
GET /timesheet/{email}/{system}?start_date=2024-01-01&end_date=2024-01-07
```

## Usage Examples

### 1. System Selection
```json
{
    "email": "john.doe@company.com",
    "user_prompt": "I want to use Oracle system"
}
```

### 2. Fill Timesheet - Simple
```json
{
    "email": "john.doe@company.com",
    "user_prompt": "Add 8 hours for ORG-001 yesterday"
}
```

### 3. Fill Timesheet - Multiple Days
```json
{
    "email": "john.doe@company.com",
    "user_prompt": "Fill 8 hours daily for ORG-001 this week"
}
```

### 4. Natural Language Dates
```json
{
    "email": "john.doe@company.com",
    "user_prompt": "I worked 6 hours on Mars project MRS-001 last Monday"
}
```

### 5. View Timesheet
```json
{
    "email": "john.doe@company.com",
    "user_prompt": "Show my Oracle timesheet for this week"
}
```

### 6. Get Project Codes
```json
{
    "email": "john.doe@company.com",
    "user_prompt": "What Oracle projects are available?"
}
```

### 7. Copy Previous Week
```json
{
    "email": "john.doe@company.com",
    "user_prompt": "Copy last week's timesheet to this week"
}
```

### 8. Complex Request
```json
{
    "email": "john.doe@company.com",
    "user_prompt": "I need to fill my Mars timesheet: 8 hours on MRS-001 for Monday and Tuesday, 6 hours on MRS-002 Wednesday, and 4 hours documentation on CMN-002 for Thursday and Friday"
}
```

## Response Format

```json
{
    "response": "I've successfully added your timesheet entries! Here's what I saved:",
    "html_content": "<div class='timesheet-container'>...</div>",
    "system_selected": "Oracle",
    "session_id": "session_john.doe@company.com"
}
```

## Natural Language Processing Features

### Supported Date Formats
- **Relative dates**: yesterday, today, tomorrow
- **Day names**: Monday, Tuesday, last Friday, next Wednesday
- **Week references**: this week, last week, next week
- **Specific dates**: 2024-01-15, January 15th, 01/15/2024

### Supported Time Expressions
- **Hours**: 8 hours, 8h, 8 hrs
- **Project codes**: ORG-001, MRS-002, CMN-001
- **Multiple entries**: Automatically handles complex requests

### Conversation Context
- Remembers selected system across conversation
- Maintains conversation history for context
- Handles follow-up questions and clarifications
- Supports session management across devices

## Troubleshooting

### Common Issues

1. **Ollama Connection Error**
   ```bash
   # Check if Ollama is running
   ollama list

   # Start Ollama service
   ollama serve
   ```

2. **Database Connection Error**
   ```bash
   # Test SQL Server connection
   sqlcmd -S localhost -U sa -P YourPassword123

   # Check ODBC drivers
   odbcinst -q -d
   ```

3. **Model Not Found**
   ```bash
   # Pull the required model
   ollama pull llama3.2:1b

   # List available models
   ollama list
   ```

## Production Deployment

### Security Considerations
- Change default passwords
- Use environment variables for sensitive data
- Enable HTTPS/TLS
- Implement rate limiting
- Add authentication middleware

### Performance Optimization
- Use connection pooling
- Implement caching for project codes
- Monitor memory usage with Ollama
- Scale with multiple workers

### Monitoring
- Health check endpoint: `/health`
- Logs are output to stdout
- Monitor database connections
- Track API response times

## Development

### Running Tests
```bash
# Install test dependencies
pip install pytest httpx pytest-asyncio

# Run tests
pytest tests/ -v
```

### Code Structure
```
├── main.py                 # FastAPI application
├── timesheet_database_schema.sql  # Database schema
├── requirements.txt        # Python dependencies
├── Dockerfile             # Container configuration
├── docker-compose.yml     # Multi-service setup
├── .env.template          # Environment template
└── README.md              # This file
```

## API Documentation

Once the server is running, visit:
- **Interactive API docs**: http://localhost:8000/docs
- **ReDoc documentation**: http://localhost:8000/redoc

## Support

For issues and questions:
1. Check the health endpoint: `/health`
2. Review application logs
3. Verify Ollama model availability
4. Test database connectivity

---

**Note**: This is a production-ready backend that requires a frontend chat interface to be fully functional. The API returns both conversational responses and HTML-formatted tables for timesheet display.
