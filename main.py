import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson.objectid import ObjectId
from datetime import datetime

from database import db, create_document, get_documents
from schemas import Event, Bettor, Bet

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helpers to convert ObjectId

def oid(val: str) -> ObjectId:
    try:
        return ObjectId(val)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")


def serialize(doc):
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    # Convert datetimes to isoformat strings for JSON
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


@app.get("/")
def read_root():
    return {"message": "Betting API is live"}


# Seed sample events for demo
@app.post("/api/seed")
def seed_events():
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    now = datetime.utcnow()
    events = [
        {
            "title": "Team Red vs Team Blue",
            "category": "Soccer",
            "start_time": now,
            "status": "open",
            "outcomes": [
                {"name": "Team Red", "odds": 1.9},
                {"name": "Draw", "odds": 3.2},
                {"name": "Team Blue", "odds": 2.1},
            ],
        },
        {
            "title": "Fighter A vs Fighter B",
            "category": "MMA",
            "start_time": now,
            "status": "open",
            "outcomes": [
                {"name": "Fighter A", "odds": 1.6},
                {"name": "Fighter B", "odds": 2.4},
            ],
        },
    ]

    inserted_ids = []
    for ev in events:
        ev_doc = ev.copy()
        ev_doc["created_at"] = datetime.utcnow()
        ev_doc["updated_at"] = datetime.utcnow()
        res = db["event"].insert_one(ev_doc)
        inserted_ids.append(str(res.inserted_id))

    return {"inserted": inserted_ids}


@app.get("/api/events")
def list_events():
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    docs = list(db["event"].find({}).sort("start_time", 1).limit(50))
    return [serialize(d) for d in docs]


class CreateBettor(BaseModel):
    display_name: str


@app.post("/api/bettors")
def create_bettor(payload: CreateBettor):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    bettor = Bettor(display_name=payload.display_name)
    new_id = create_document("bettor", bettor)
    return {"id": new_id}


@app.get("/api/bettors/{bettor_id}")
def get_bettor(bettor_id: str):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    doc = db["bettor"].find_one({"_id": oid(bettor_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Bettor not found")
    return serialize(doc)


class PlaceBet(BaseModel):
    bettor_id: str
    event_id: str
    outcome: str
    amount: float


@app.post("/api/bets")
def place_bet(payload: PlaceBet):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    bettor = db["bettor"].find_one({"_id": oid(payload.bettor_id)})
    if not bettor:
        raise HTTPException(status_code=404, detail="Bettor not found")

    event = db["event"].find_one({"_id": oid(payload.event_id)})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.get("status") != "open":
        raise HTTPException(status_code=400, detail="Event not open for betting")

    # Find odds for the selected outcome
    chosen = None
    for o in event.get("outcomes", []):
        if o.get("name") == payload.outcome:
            chosen = o
            break
    if not chosen:
        raise HTTPException(status_code=400, detail="Invalid outcome for this event")

    amount = float(payload.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid bet amount")

    # Play-money balance check
    balance = float(bettor.get("balance", 1000.0))
    if amount > balance:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    potential = round(amount * float(chosen.get("odds")), 2)

    bet = Bet(
        user_id=str(bettor["_id"]),
        event_id=str(event["_id"]),
        outcome=payload.outcome,
        amount=amount,
        odds_at_bet=float(chosen.get("odds")),
        potential_payout=potential,
    )
    bet_id = create_document("bet", bet)

    # Deduct balance
    db["bettor"].update_one({"_id": bettor["_id"]}, {"$inc": {"balance": -amount}, "$set": {"updated_at": datetime.utcnow()}})

    return {"id": bet_id, "potential_payout": potential}


@app.get("/api/bettors/{bettor_id}/bets")
def list_bets(bettor_id: str):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    bets = list(db["bet"].find({"user_id": bettor_id}).sort("created_at", -1))
    return [serialize(b) for b in bets]


class SettleEvent(BaseModel):
    event_id: str
    result: str


@app.post("/api/events/settle")
def settle_event(payload: SettleEvent):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    ev = db["event"].find_one({"_id": oid(payload.event_id)})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    # validate result exists among outcomes
    if not any(o.get("name") == payload.result for o in ev.get("outcomes", [])):
        raise HTTPException(status_code=400, detail="Result is not a valid outcome")

    db["event"].update_one(
        {"_id": ev["_id"]},
        {"$set": {"status": "settled", "result": payload.result, "updated_at": datetime.utcnow()}},
    )

    # Pay out bets
    winning_bets = list(db["bet"].find({"event_id": str(ev["_id"]), "outcome": payload.result}))
    for b in winning_bets:
        payout = float(b.get("amount", 0)) * float(b.get("odds_at_bet", 0))
        payout = round(payout, 2)
        db["bet"].update_one({"_id": b["_id"]}, {"$set": {"status": "won", "settled_payout": payout, "updated_at": datetime.utcnow()}})
        db["bettor"].update_one({"_id": oid(b["user_id"] )}, {"$inc": {"balance": payout}})

    # Mark losing bets
    db["bet"].update_many(
        {"event_id": str(ev["_id"]), "outcome": {"$ne": payload.result}},
        {"$set": {"status": "lost", "settled_payout": 0.0, "updated_at": datetime.utcnow()}},
    )

    return {"status": "settled"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
