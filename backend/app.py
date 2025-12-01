"""
AI HR Psychologist - Multi-tests Backend (PLUS)
----------------------------------------------
+ Кандидати, результати тестів
+ Голосовий аналіз (стрес)
+ Фотоаналіз (настрій / втома)
+ HR-панель (ендпоінти /api/hr/...)
+ Проста HR-авторизація через заголовок X-Admin-Key
+ Простий білінг (free / pro_demo + demo_until)
"""

import io
import os
import json
import datetime
from statistics import mean
import matplotlib.pyplot as plt
import tempfile
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ai.voice import analyze_voice_bytes
from ai.photo import analyze_photo_bytes
from ai.reports import build_pdf_report

DB_PATH = Path(__file__).resolve().parent / "hrpsy_multi_plus.db"
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "DEV_ADMIN_KEY")

app = FastAPI(title="AI HR Psychologist Backend (PLUS)", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def check_admin(api_key: Optional[str]):
    if api_key is None or api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized (invalid X-Admin-Key)")


SUPPORTED_TESTS: Dict[str, Dict[str, Any]] = {
    "bigfive": {
        "name": "Big Five (OCEAN)",
        "traits": {
            "O": "Відкритість досвіду",
            "C": "Сумлінність",
            "E": "Екстраверсія",
            "A": "Доброзичливість",
            "N": "Емоційна стабільність",
        },
    },
    "mbti": {
        "name": "MBTI",
        "traits": {
            "EI": "Екстраверсія–Інтроверсія",
            "SN": "Сенсорика–Інтуїція",
            "TF": "Логіка–Почуття",
            "JP": "Планування–Спонтанність",
        },
    },
    "belbin": {
        "name": "Ролі Белбіна",
        "traits": {
            "PL": "Генератор ідей",
            "CO": "Координатор",
            "IMP": "Виконавець",
            "TW": "Командний гравець",
        },
    },
    "eq": {
        "name": "Емоційний інтелект (EQ)",
        "traits": {
            "SA": "Самосвідомість",
            "SR": "Самоконтроль",
            "EM": "Емпатія",
            "SS": "Соціальні навички",
        },
    },
    "ponomarenko": {
        "name": "Радикали (Пономаренко)",
        "traits": {
            "DOM": "Домінантність / воля",
            "EMO": "Емоційність / вибуховість",
            "ANX": "Тривожність / чутливість",
            "SOC": "Соціальність / контактність",
        },
    },
}


def list_tests_meta() -> List[Dict[str, Any]]:
    out = []
    for code, meta in SUPPORTED_TESTS.items():
        out.append({"code": code, "name": meta["name"], "traits": meta["traits"]})
    return out


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            full_name TEXT,
            created_at TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            test_type TEXT,
            raw_answers TEXT,
            scores_json TEXT,
            created_at TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            test_type TEXT,
            summary TEXT,
            recommendations TEXT,
            risk_level TEXT,
            created_at TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS voice_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            stress_score REAL,
            level TEXT,
            details_json TEXT,
            created_at TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS photo_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            mood TEXT,
            fatigue_level TEXT,
            brightness REAL,
            contrast REAL,
            created_at TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_billing (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            email TEXT,
            plan TEXT,
            demo_until TEXT
        )
        """
    )

    c.execute("SELECT COUNT(*) FROM hr_billing")
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO hr_billing (id, email, plan, demo_until) VALUES (1, ?, ?, ?)",
            ("demo@example.com", "free", None),
        )

    conn.commit()
    conn.close()


init_db()


class StartTestRequest(BaseModel):
    tg_id: int
    full_name: Optional[str] = None


class StartTestResponse(BaseModel):
    candidate_id: int


class SubmitTestRequest(BaseModel):
    candidate_id: int
    test_type: str
    answers: List[int]

class CandidateDTO(BaseModel):
    id: int
    tg_id: int
    full_name: str
    created_at: str

class CandidateDetailDTO(BaseModel):
    candidate: CandidateDTO
    tests: List[TestResultDTO] = []
    reports: List[dict] = []
    voices: List[VoiceResultDTO] = []
    photos: List[PhotoResultDTO] = []


class TestResultDTO(BaseModel):
    id: int
    candidate_id: int
    test_type: str
    scores: dict
    created_at: str


class VoiceResultDTO(BaseModel):
    id: int
    candidate_id: int
    stress_score: float
    level: str
    created_at: str


class PhotoResultDTO(BaseModel):
    id: int
    candidate_id: int
    mood: str
    fatigue_level: str
    brightness: float
    contrast: float
    created_at: str

class ProgressReport(BaseModel):
    emotional_stability: str
    stress_trend: str
    fatigue_trend: str
    overall_change: str
    details: dict



class BillingStatus(BaseModel):
    email: str
    plan: str
    demo_until: Optional[str]


def _chunk_scores(answers: List[int], trait_keys: List[str]) -> Dict[str, float]:
    if not answers:
        answers = [3]
    n_traits = max(1, len(trait_keys))
    chunk_size = max(1, len(answers) // n_traits)
    scores: Dict[str, float] = {}
    for i, key in enumerate(trait_keys):
        start = i * chunk_size
        end = start + chunk_size
        chunk = answers[start:end] if start < len(answers) else []
        if not chunk:
            scores[key] = 3.0
        else:
            scores[key] = float(sum(chunk) / len(chunk))
    return scores


def compute_scores_for_test(test_type: str, answers: List[int]) -> Dict[str, float]:
    if test_type not in SUPPORTED_TESTS:
        return _chunk_scores(answers, ["T1", "T2", "T3"])
    trait_keys = list(SUPPORTED_TESTS[test_type]["traits"].keys())
    return _chunk_scores(answers, trait_keys)


def _trait_level(x: float) -> str:
    if x >= 4.0:
        return "високий"
    if x <= 2.0:
        return "низький"
    return "середній"


def generate_hr_report(test_type: str, scores: Dict[str, float]) -> Dict[str, Any]:
    meta = SUPPORTED_TESTS.get(test_type)
    test_name = meta["name"] if meta else test_type

    sorted_traits = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top = []
    for code, val in sorted_traits[:2]:
        label = meta["traits"].get(code, code) if meta else code
        top.append(f"{label} — {_trait_level(val)} рівень")
    summary = f"{test_name}: " + ("; ".join(top) if top else "без виражених акцентів.")

    recs: List[str] = []
    risk = "низький"

    if test_type == "bigfive":
        c = scores.get("C", 3.0)
        e = scores.get("E", 3.0)
        n = scores.get("N", 3.0)
        if c >= 3.5:
            recs.append("Підходить для відповідальних, структурованих задач.")
        else:
            recs.append("Потребує чітких дедлайнів і контролю.")
        if e >= 3.5:
            recs.append("Комфортно в активних комунікаціях.")
        else:
            recs.append("Краще для зосередженої, індивідуальної роботи.")
        if n >= 3.8:
            risk = "високий"
        elif n >= 3.2:
            risk = "середній"
    elif test_type == "eq":
        sr = scores.get("SR", 3.0)
        if sr < 2.5:
            risk = "середній"
            recs.append("Бажано розвивати навички емоційної саморегуляції.")
        else:
            recs.append("Має базовий або високий рівень контролю емоцій.")
    elif test_type == "ponomarenko":
        emo = scores.get("EMO", 3.0)
        anx = scores.get("ANX", 3.0)
        if emo + anx >= 7.0:
            risk = "високий"
        elif emo + anx >= 6.0:
            risk = "середній"
        recs.append("Рекомендується враховувати емоційні реакції та стресові чинники.")

    if not recs:
        recs.append("Інтерпретація потребує доповнення іншими спостереженнями та тестами.")

    return {"summary": summary, "recommendations": recs, "risk_level": risk}


@app.get("/")
def root():
    return {"status": "ok", "message": "AI HR Backend PLUS running"}


@app.get("/api/tests")
def api_tests_list(x_admin_key: Optional[str] = Header(None)):
    check_admin(x_admin_key)
    return list_tests_meta()


@app.post("/api/candidate/start_test", response_model=StartTestResponse)
def start_test(payload: StartTestRequest):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO candidates (tg_id, full_name, created_at) VALUES (?, ?, ?)",
        (payload.tg_id, payload.full_name or "", datetime.datetime.utcnow().isoformat()),
    )
    candidate_id = c.lastrowid
    conn.commit()
    conn.close()
    return StartTestResponse(candidate_id=candidate_id)


@app.post("/api/candidate/submit_test")
def submit_test(payload: SubmitTestRequest):
    if payload.test_type not in SUPPORTED_TESTS:
        raise HTTPException(status_code=400, detail="Unsupported test_type")

    scores = compute_scores_for_test(payload.test_type, payload.answers)
    report_dict = generate_hr_report(payload.test_type, scores)

    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()

    c.execute(
        """
        INSERT INTO test_results (candidate_id, test_type, raw_answers, scores_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            payload.candidate_id,
            payload.test_type,
            json.dumps(payload.answers, ensure_ascii=False),
            json.dumps(scores, ensure_ascii=False),
            now,
        ),
    )

    c.execute(
        """
        INSERT INTO ai_reports (candidate_id, test_type, summary, recommendations, risk_level, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            payload.candidate_id,
            payload.test_type,
            report_dict["summary"],
            json.dumps(report_dict["recommendations"], ensure_ascii=False),
            report_dict["risk_level"],
            now,
        ),
    )

    conn.commit()
    conn.close()
    return {"status": "ok", "scores": scores, "report": report_dict}


@app.post("/api/voice/analyze")
async def voice_analyze(
    candidate_id: int = Form(...),
    file: UploadFile = File(...),
):
    raw = await file.read()
    result = analyze_voice_bytes(raw, file.content_type or file.filename)

    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute(
        """
        INSERT INTO voice_results (candidate_id, stress_score, level, details_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            float(result["stress_score"]),
            result["level"],
            json.dumps(result, ensure_ascii=False),
            now,
        ),
    )
    conn.commit()
    conn.close()

    return {"status": "ok", "candidate_id": candidate_id, "voice": result}


@app.post("/api/photo/analyze")
async def photo_analyze(
    candidate_id: int = Form(...),
    file: UploadFile = File(...),
):
    raw = await file.read()
    result = analyze_photo_bytes(raw)

    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute(
        """
        INSERT INTO photo_results (candidate_id, mood, fatigue_level, brightness, contrast, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            result["mood"],
            result["fatigue_level"],
            float(result["brightness"]),
            float(result["contrast"]),
            now,
        ),
    )
    conn.commit()
    conn.close()

    return {"status": "ok", "candidate_id": candidate_id, "photo": result}


@app.get("/api/hr/candidates", response_model=List[CandidateDTO])
def list_candidates(x_admin_key: Optional[str] = Header(None)):
    check_admin(x_admin_key)
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, tg_id, full_name, created_at FROM candidates ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return [
        CandidateDTO(id=row[0], tg_id=row[1], full_name=row[2], created_at=row[3])
        for row in rows
    ]


@app.get("/api/hr/candidate/{candidate_id}", response_model=CandidateDetailDTO)
def get_candidate(candidate_id: int, x_admin_key: Optional[str] = Header(None)):
    check_admin(x_admin_key)
    conn = get_conn()
    c = conn.cursor()

    # Candidate
    c.execute("SELECT id, tg_id, full_name, created_at FROM candidates WHERE id = ?", (candidate_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate = CandidateDTO(id=row[0], tg_id=row[1], full_name=row[2], created_at=row[3])

    # ALL TEST RESULTS
    c.execute("""
        SELECT id, candidate_id, test_type, scores_json, created_at
        FROM test_results
        WHERE candidate_id = ?
        ORDER BY id DESC
    """, (candidate_id,))
    tests = [
        TestResultDTO(
            id=r[0], candidate_id=r[1], test_type=r[2],
            scores=json.loads(r[3]), created_at=r[4]
        )
        for r in c.fetchall()
    ]

    # ALL REPORTS
    c.execute("""
        SELECT test_type, summary, recommendations, risk_level, created_at
        FROM ai_reports
        WHERE candidate_id = ?
        ORDER BY id DESC
    """, (candidate_id,))
    reports = [
        {
            "test_type": r[0],
            "summary": r[1],
            "recommendations": json.loads(r[2]),
            "risk_level": r[3],
            "created_at": r[4],
        }
        for r in c.fetchall()
    ]

    # ALL VOICE ANALYSIS
    c.execute("""
        SELECT id, candidate_id, stress_score, level, created_at
        FROM voice_results
        WHERE candidate_id = ?
        ORDER BY id DESC
    """, (candidate_id,))
    voices = [
        VoiceResultDTO(
            id=r[0], candidate_id=r[1], stress_score=r[2],
            level=r[3], created_at=r[4]
        )
        for r in c.fetchall()
    ]

    # ALL PHOTO ANALYSIS
    c.execute("""
        SELECT id, candidate_id, mood, fatigue_level, brightness, contrast, created_at
        FROM photo_results
        WHERE candidate_id = ?
        ORDER BY id DESC
    """, (candidate_id,))
    photos = [
        PhotoResultDTO(
            id=r[0], candidate_id=r[1], mood=r[2],
            fatigue_level=r[3], brightness=r[4],
            contrast=r[5], created_at=r[6]
        )
        for r in c.fetchall()
    ]

    conn.close()

    return CandidateDetailDTO(
        candidate=candidate,
        tests=tests,
        reports=reports,
        voices=voices,
        photos=photos,
    )


@app.get("/api/hr/stats/{candidate_id}")
def candidate_stats(candidate_id: int, x_admin_key: Optional[str] = Header(None)):
    check_admin(x_admin_key)

    conn = get_conn()
    c = conn.cursor()

    # stress timeline
    c.execute("""
        SELECT stress_score, created_at
        FROM voice_results
        WHERE candidate_id=?
        ORDER BY id ASC
    """, (candidate_id,))
    voice_rows = c.fetchall()

    stress = [{"score": r[0], "ts": r[1]} for r in voice_rows]

    # photo timeline
    c.execute("""
        SELECT fatigue_level, brightness, contrast, created_at
        FROM photo_results
        WHERE candidate_id=?
        ORDER BY id ASC
    """, (candidate_id,))
    photo_rows = c.fetchall()

    photo = [{
        "fatigue": r[0],
        "brightness": r[1],
        "contrast": r[2],
        "ts": r[3]
    } for r in photo_rows]

    # test timelines
    c.execute("""
        SELECT test_type, scores_json, created_at
        FROM test_results
        WHERE candidate_id=?
        ORDER BY id ASC
    """, (candidate_id,))
    test_rows = c.fetchall()

    tests = []
    for ttype, js, ts in test_rows:
        tests.append({
            "test_type": ttype,
            "scores": json.loads(js),
            "ts": ts
        })

    conn.close()

    return {
        "stress": stress,
        "photo": photo,
        "tests": tests
    }
     
@app.get("/api/hr/progress/{candidate_id}", response_model=ProgressReport)
def hr_progress(candidate_id: int, x_admin_key: Optional[str] = Header(None)):
    check_admin(x_admin_key)

    conn = get_conn()
    c = conn.cursor()

    # Fetch tests
    c.execute("""
        SELECT scores_json
        FROM test_results
        WHERE candidate_id=?
        ORDER BY id ASC
    """, (candidate_id,))
    test_rows = [json.loads(r[0]) for r in c.fetchall()]

    # Voice
    c.execute("""
        SELECT stress_score
        FROM voice_results
        WHERE candidate_id=?
        ORDER BY id ASC
    """, (candidate_id,))
    voice = [r[0] for r in c.fetchall()]

    # Photo fatigue
    c.execute("""
        SELECT fatigue_level
        FROM photo_results
        WHERE candidate_id=?
        ORDER BY id ASC
    """, (candidate_id,))
    fatigue = [float(r[0]) for r in c.fetchall()]

    conn.close()

    # Calculate
    emotional_change = ""
    stress_trend = ""
    fatigue_trend = ""

    if len(test_rows) >= 2:
        first = mean(test_rows[0].values())
        last = mean(test_rows[-1].values())
        emotional_change = (
            "Покращення емоційної стабільності" if last > first
            else "Погіршення емоційної стабільності"
        )

    if len(voice) >= 2:
        stress_trend = (
            "Стрес зменшується" if voice[-1] < voice[0]
            else "Стрес зростає"
        )

    if len(fatigue) >= 2:
        fatigue_trend = (
            "Втома зменшується" if fatigue[-1] < fatigue[0]
            else "Втома збільшується"
        )

    return ProgressReport(
        emotional_stability=emotional_change or "Недостатньо даних",
        stress_trend=stress_trend or "Недостатньо даних",
        fatigue_trend=fatigue_trend or "Недостатньо даних",
        overall_change="Покращення" if emotional_change.startswith("Пок") else "Погіршення",
        details={
            "tests_count": len(test_rows),
            "voice_count": len(voice),
            "photo_count": len(fatigue)
        }
    )


@app.get("/api/billing/status", response_model=BillingStatus)
def billing_status(x_admin_key: Optional[str] = Header(None)):
    check_admin(x_admin_key)
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT email, plan, demo_until FROM hr_billing WHERE id=1")
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=500, detail="Billing not initialized")
    return BillingStatus(email=row[0], plan=row[1], demo_until=row[2])       
       
            
@app.post("/api/billing/activate_demo", response_model=BillingStatus)
def billing_activate_demo(days: int = 14, x_admin_key: Optional[str] = Header(None)):
    check_admin(x_admin_key)
    demo_until = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE hr_billing SET plan=?, demo_until=? WHERE id=1",
        ("pro_demo", demo_until),
    )
    conn.commit()
    c.execute("SELECT email, plan, demo_until FROM hr_billing WHERE id=1")
    row = c.fetchone()
    conn.close()
    return BillingStatus(email=row[0], plan=row[1], demo_until=row[2])

@app.get("/api/hr/candidate/{candidate_id}/pdf")
def pdf_full(candidate_id: int, x_admin_key: Optional[str] = Header(None)):
    check_admin(x_admin_key)

    # reuse existing endpoint
    detail = get_candidate(candidate_id, x_admin_key)

    # generate PDF with your existing builder
    pdf_bytes = build_pdf_report(detail.dict())

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=candidate_{candidate_id}_full.pdf"}
    )