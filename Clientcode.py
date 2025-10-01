import requests

BASE_URL = "http://localhost:8000"

def fill_timesheet(email: str, prompt: str):
    """Send a free-text prompt to FastAPI server"""
    url = f"{BASE_URL}/fill-timesheet"
    payload = {"email": email, "prompt": prompt}
    r = requests.post(url, json=payload)
    if r.status_code == 200:
        return r.json()
    else:
        raise Exception(f"Error {r.status_code}: {r.text}")

def get_history(email: str):
    """Fetch history of all submissions for this user (if enabled on server)"""
    url = f"{BASE_URL}/history/{email}"
    r = requests.get(url)
    if r.status_code == 200:
        return r.json()
    else:
        raise Exception(f"Error {r.status_code}: {r.text}")

if __name__ == "__main__":
    # Example usage
    email = "alice@example.com"

    # Step 1: Provide project
    print("➡ Project:")
    res = fill_timesheet(email, "Working on Project Apollo")
    print(res)

    # Step 2: Provide date
    print("\n➡ Date:")
    res = fill_timesheet(email, "on 1st October 2025")
    print(res)

    # Step 3: Provide hours + system
    print("\n➡ Hours + System:")
    res = fill_timesheet(email, "Worked 5 hours in Oracle")
    print(res)

    # Final record will be inserted into OracleTimesheet table
    print("\n✅ Final Result:", res)

    # Optional: check history
    # print(get_history(email))
