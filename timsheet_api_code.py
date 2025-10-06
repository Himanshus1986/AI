from fastapi import FastAPI, Request
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import pyodbc
import requests, json, os
from datetime import datetime
from langchain_community.llms import Ollama
from fastapi import HTTPException
from sqlalchemy import create_engine
import json
import re

app = FastAPI()

def get_pyodbc_conn():
    return pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=Indelsrv140\\Intellego,1113;"  # Replace with your server name
    "DATABASE=Intellego_PreProd;"  # Replace with your database name
    "UID=Intellego_USR;"  # Replace with your SQL username
    "PWD=admin@123;"  # Replace with your SQL password
    )   

# 🔹 Adjust with your SQL Server details

# ORM for session tracking
engine = create_engine("mssql+pyodbc://", creator=get_pyodbc_conn)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()



class TimesheetSession(Base):
    __tablename__ = "timesheet_sessions"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True)
    data = Column(Text)   # JSON as text
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

Base.metadata.create_all(bind=engine)

llm = Ollama(model="llama3.2:1b")

# 🧠 Parse free text with Llama 3.2 1B
def parse__artial(prompt: str):
    full_prompt = f"""
    Extract timesheet details from: "{prompt}".
    Return JSON with only available fields:
    - date (YYYY-MM-DD)
    - hours (integer)
    - project (string)
    - comments (string)
    - system (Oracle or Mars)
    """
    try:
        result_text = llm.generate(full_prompt)["response"].strip()
        return json.loads(result_text)
    except Exception:
        return {}

def parse____partial(prompt: str):
    full_prompt = f"""
You are a timesheet parser. Extract structured data from the following input: "{prompt}"

Return a valid JSON object with any of the following fields that are clearly mentioned:
- date (format: YYYY-MM-DD)
- hours (integer)
- project (string)
- comments (string)
- system (must be either "Oracle" or "Mars")

If the word "Oracle" or "Mars" appears in the input, assume it refers to the system and include it as the "system" field.

Only return the JSON object. Do not include any explanation or formatting.
"""

    try:
        result = llm.generate([full_prompt])
        raw_text = result.generations[0][0].text.strip()
        print("🧾 Raw LLM response:", raw_text)

        # Extract JSON block using regex
        match = re.search(r"\{.*?\}", raw_text, re.DOTALL)
        if match:
            json_text = match.group(0)
            parsed = json.loads(json_text)
            return parsed
        else:
            print("⚠️ No JSON block found in response")
            return {}

    except json.JSONDecodeError as e:
        print("❌ JSON parsing error:", e)
        return {}

    except Exception as e:
        print("❌ Unexpected error:", e)
        return {}

def parse_partial(prompt: str):
    full_prompt = f"""
You are a timesheet parser. Extract structured data from the following input: "{prompt}"

Return a valid JSON object with ONLY the fields that are clearly and explicitly mentioned.

Allowed fields:
- date (format: YYYY-MM-DD)
- hours (integer)
- project (string)
- comments (string)
- system (must be either "Oracle" or "Mars")

⚠️ Do NOT guess or assume values. If a field is not clearly mentioned, do not include it.

Only return the JSON object. No explanation, no formatting.
"""

    try:
        result = llm.generate([full_prompt])
        raw_text = result.generations[0][0].text.strip()
        print("🧾 Raw LLM response:", raw_text)

        match = re.search(r"\{.*?\}", raw_text, re.DOTALL)
        if not match:
            print("⚠️ No JSON block found in response")
            return {}

        json_text = match.group(0)
        parsed = json.loads(json_text)

        # 🔍 Filter out default/hallucinated values
        filtered = {}
        if "date" in parsed and re.search(r"\d{4}-\d{2}-\d{2}", prompt):
            filtered["date"] = parsed["date"]
        if "hours" in parsed and re.search(r"\b\d+\s*(hours|hrs)\b", prompt, re.IGNORECASE):
            filtered["hours"] = parsed["hours"]
        if "project" in parsed and re.search(r"\b(project|worked on|task)\b", prompt, re.IGNORECASE):
            filtered["project"] = parsed["project"]
        if "comments" in parsed and re.search(r"\b(comment|note|feedback)\b", prompt, re.IGNORECASE):
            filtered["comments"] = parsed["comments"]
        if "system" in parsed and re.search(r"\b(oracle|mars)\b", prompt, re.IGNORECASE):
            filtered["system"] = parsed["system"]

        return filtered

    except Exception as e:
        print("❌ Error in parse_partial:", e)
        return {}
# Direct connection for inserts


# 🔹 Insert into OracleTimesheet table
def submit_to_oracle(timesheet: dict, email: str):
    conn = get_pyodbc_conn()
    cursor = conn.cursor()
    sql = """
        INSERT INTO OracleTimesheet (email, work_date, hours, project, comments)
        VALUES (?, ?, ?, ?, ?)
    """
    cursor.execute(
        sql,
        email,
        timesheet.get("date"),
        timesheet.get("hours"),
        timesheet.get("project"),
        timesheet.get("comments"),
    )
    conn.commit()
    conn.close()
    return {"system": "Oracle", "status": "Inserted", "sql": sql}

# 🔹 Insert into MarsTimesheet table
def submit_to_mars(timesheet: dict, email: str):
    conn = get_pyodbc_conn()
    cursor = conn.cursor()
    sql = """
        INSERT INTO MarsTimesheet (email, work_date, hours, project, comments)
        VALUES (?, ?, ?, ?, ?)
    """
    cursor.execute(
        sql,
        email,
        timesheet.get("date"),
        timesheet.get("hours"),
        timesheet.get("project"),
        timesheet.get("comments"),
    )
    conn.commit()
    conn.close()
    return {"system": "Mars", "status": "Inserted", "sql": sql}
"""
@app.post("/fill-timesheet")
async def fill_timesheet(req: Request):
    body = await req.json()
    email = body.get("email")
    prompt = body.get("prompt")
    print("reached here")
    print(prompt)

    if not email:
        return {"error": "Email is required"}

    db = SessionLocal()
    session = db.query(TimesheetSession).filter_by(email=email).first()

    if not session:
        session = TimesheetSession(email=email, data=json.dumps({}))
        db.add(session)
        db.commit()
        db.refresh(session)

    # Parse partial input
    parsed = parse_partial(prompt)
    
    print("parsed")
    print(parsed)
    
    current_data = json.loads(session.data or "{}")
    current_data.update(parsed)

    session.data = json.dumps(current_data)
    db.commit()

    required = ["date", "hours", "project", "system"]
    missing = [f for f in required if f not in current_data]

    result = {"email": email, "session": current_data, "missing": missing}

    # If all info present → insert into proper table
    if not missing:
        if current_data["system"].lower() == "oracle":
            result["results"] = [submit_to_oracle(current_data, email)]
            session.data = "{}"
        elif current_data["system"].lower() == "mars":
            result["results"] = [submit_to_mars(current_data, email)]
            session.data = "{}"
        else:
            result["results"] = [
                submit_to_oracle(current_data, email),
                submit_to_mars(current_data, email),
            ]
            session.data = "{}"

        # Optional: clear session after submission
        # session.data = "{}"
        # db.commit()

    db.close()
    return result
"""


@app.post("/fill-timesheet")
async def fill_timesheet(req: Request):
    body = await req.json()
    email = body.get("email")
    prompt = body.get("prompt")
    print(prompt)
    if not email:
        return {"error": "Email is required"}

    db = SessionLocal()
    session = db.query(TimesheetSession).filter_by(email=email).first()

    if not session:
        session = TimesheetSession(email=email, data=json.dumps({}))
        db.add(session)
        db.commit()
        db.refresh(session)

    # Parse only what's mentioned in the prompt
    parsed = parse_partial(prompt)
    print("🔍 Parsed from prompt:", parsed)

    # Load current session data
    current_data = json.loads(session.data or "{}")

    # Update only with newly parsed fields
    for key in parsed:
        current_data[key] = parsed[key]

    # Save updated session
    session.data = json.dumps(current_data)
    db.commit()

    # Required fields
    required = ["date", "hours", "project", "system"]
    missing = [field for field in required if field not in current_data]

    result = {
        "email": email,
        "session": current_data,
        "missing": missing
    }

    # Submit only if all required fields are present
    if not missing:
        system = current_data.get("system", "").lower()
        if system == "oracle":
            result["results"] = [submit_to_oracle(current_data, email)]
        elif system == "mars":
            result["results"] = [submit_to_mars(current_data, email)]
        """else:
            result["results"] = [
                submit_to_oracle(current_data, email),
                submit_to_mars(current_data, email)
            ]
        """
        # Clear session after submission
        session.data = "{}"
        db.commit()

    db.close()
    return result

# 🔹 Fetch all history for a user
@app.get("/history/{email}")
async def get_history(email: str):
    conn = get_pyodbc_conn()
    cursor = conn.cursor()

    history = {"oracle": [], "mars": []}

    # Oracle history
    cursor.execute("""
        SELECT id, email, work_date, hours, project, comments, created_at
        FROM OracleTimesheet WHERE email = ?
        ORDER BY created_at DESC
    """, email)
    for row in cursor.fetchall():
        history["oracle"].append({
            "id": row.id,
            "email": row.email,
            "date": str(row.work_date),
            "hours": row.hours,
            "project": row.project,
            "comments": row.comments,
            "created_at": str(row.created_at)
        })

    # Mars history
    cursor.execute("""
        SELECT id, email, work_date, hours, project, comments, created_at
        FROM MarsTimesheet WHERE email = ?
        ORDER BY created_at DESC
    """, email)
    for row in cursor.fetchall():
        history["mars"].append({
            "id": row.id,
            "email": row.email,
            "date": str(row.work_date),
            "hours": row.hours,
            "project": row.project,
            "comments": row.comments,
            "created_at": str(row.created_at)
        })

    conn.close()

    if not history["oracle"] and not history["mars"]:
        raise HTTPException(status_code=404, detail="No history found for this email")

    return history
