"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# Example schemas (replace with your own):

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Betting site schemas

class Outcome(BaseModel):
    name: str = Field(..., description="Outcome label, e.g., Team A")
    odds: float = Field(..., gt=1.0, description="Decimal odds, e.g., 1.80")

class Event(BaseModel):
    title: str = Field(..., description="Event title")
    category: str = Field(..., description="Sport or category")
    start_time: datetime = Field(..., description="Event start time")
    status: str = Field("open", description="open | closed | settled")
    outcomes: List[Outcome] = Field(..., description="List of possible outcomes with odds")
    result: Optional[str] = Field(None, description="Winning outcome name once settled")

class Bettor(BaseModel):
    display_name: str = Field(..., description="User display name")
    balance: float = Field(1000.0, ge=0, description="Play-money wallet balance")

class Bet(BaseModel):
    user_id: str = Field(..., description="Bettor id")
    event_id: str = Field(..., description="Event id")
    outcome: str = Field(..., description="Outcome chosen (by name)")
    amount: float = Field(..., gt=0, description="Stake amount")
    odds_at_bet: float = Field(..., gt=1.0, description="Decimal odds locked at bet time")
    status: str = Field("pending", description="pending | won | lost")
    potential_payout: float = Field(..., gt=0, description="amount * odds")
    settled_payout: Optional[float] = Field(None, description="Payout if settled")
