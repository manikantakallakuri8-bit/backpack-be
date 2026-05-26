from datetime import datetime, timedelta
from typing import Annotated
from fastapi import APIRouter, HTTPException, Depends
from passlib.context import CryptContext
from jose import JWTError, jwt
from models import UserCreate, UserLogin, TokenResponse, UserRole
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 480))


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_db() -> AsyncIOMotorDatabase:
    from main import app
    return app.state.db


@router.post("/register")
async def register(user: UserCreate):
    """Register a new user"""
    db = get_db()
    import pdb; pdb.set_trace()
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Validate operative_type
    if user.role == UserRole.operative and not user.operative_type:
        raise HTTPException(status_code=400, detail="operative_type is required when role is operative")
    
    # Create user document
    user_doc = {
        "name": user.name,
        "email": user.email,
        "password": hash_password(user.password),
        "role": user.role,
        "operative_type": user.operative_type,
        "created_at": datetime.utcnow()
    }
    
    # Save to MongoDB
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)
    
    return {
        "message": "User registered successfully",
        "user_id": user_id
    }


@router.post("/login", response_model=TokenResponse)
async def login(user: UserLogin):
    """Login user and return JWT token"""
    db = get_db()
    
    # Find user by email
    db_user = await db.users.find_one({"email": user.email})
    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Create JWT token
    token_data = {
        "sub": user.email,
        "user_id": str(db_user["_id"])
    }
    access_token = create_access_token(data=token_data)
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        role=db_user["role"],
        name=db_user["name"],
        user_id=str(db_user["_id"])
    )
