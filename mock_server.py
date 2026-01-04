"""
Mock Backend Server for PoC Testing
"""

from fastapi import FastAPI, Query
from datetime import date, datetime
from typing import Optional
import random

app = FastAPI(title="Mock Backend API", version="1.0.0")

# ═══════════════════════════════════════════════════════════════════
# Mock Data
# ═══════════════════════════════════════════════════════════════════

NAMES = ["王小明", "李美玲", "張大華", "陳淑芬", "林志偉", "黃雅婷"]
DEPARTMENTS = ["Engineering", "Sales", "HR", "Finance", "Marketing"]
POSITIONS = ["Software Engineer", "Sales Manager", "HR Specialist", "Accountant"]


# ═══════════════════════════════════════════════════════════════════
# HR APIs
# ═══════════════════════════════════════════════════════════════════


@app.get("/api/hr/interviews")
def list_interviews(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
):
    """Get interview list"""
    # Generate mock data
    count = random.randint(30, 50)
    interviews = []

    for i in range(count):
        interviews.append(
            {
                "id": 1000 + i,
                "candidate_name": random.choice(NAMES),
                "position": random.choice(POSITIONS),
                "department": random.choice(DEPARTMENTS),
                "interview_date": f"2024-12-{random.randint(1,28):02d}",
                "status": status
                or random.choice(["pending", "completed", "cancelled"]),
                "rating": random.randint(1, 5) if status == "completed" else None,
            }
        )

    # Filter
    if department:
        interviews = [i for i in interviews if i["department"] == department]
    if status:
        interviews = [i for i in interviews if i["status"] == status]

    return {
        "total": len(interviews),
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "status": status,
            "department": department,
        },
        "items": interviews,
    }


@app.get("/api/hr/employees")
def list_employees(
    keyword: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """Search employees"""
    count = random.randint(20, 40)
    employees = []

    for i in range(count):
        employees.append(
            {
                "id": 2000 + i,
                "name": random.choice(NAMES),
                "employee_id": f"EMP{2000+i:04d}",
                "department": department or random.choice(DEPARTMENTS),
                "position": random.choice(POSITIONS),
                "status": status or "active",
            }
        )

    return {"total": len(employees), "items": employees}


@app.get("/api/hr/statistics/monthly")
def get_monthly_stats(year: int = Query(...), month: int = Query(..., ge=1, le=12)):
    """Get monthly HR statistics"""
    return {
        "period": f"{year}-{month:02d}",
        "headcount": {
            "total": 156,
            "new_hires": random.randint(5, 15),
            "resignations": random.randint(1, 5),
        },
        "interviews": {
            "total": random.randint(30, 60),
            "completed": random.randint(20, 40),
            "pending": random.randint(5, 15),
        },
        "turnover_rate": round(random.uniform(0.01, 0.05), 3),
    }


# ═══════════════════════════════════════════════════════════════════
# Health Check
# ═══════════════════════════════════════════════════════════════════


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ═══════════════════════════════════════════════════════════════════
# Run Server
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
