from datetime import datetime, timedelta
from typing import Annotated, Optional
from fastapi import APIRouter, HTTPException, Depends
import httpx
from pydantic import BaseModel
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
from models import UserCreate, UserLogin, TokenResponse, UserRole, JobCreate, JobResponse, UpdatePay, JobUpdate, Vehicle, PlantItem, MaterialItem, JobLogUpdate, ResourceCreate
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import os
from dotenv import load_dotenv
from bson import ObjectId
import httpx

load_dotenv()

router = APIRouter()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 480))

# Groq API configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL")
GROQ_MODEL = os.getenv("GROQ_MODEL")


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
    # import pdb;pdb.set_trace()
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


security = HTTPBearer()


class AIAnalysisRequest(BaseModel):
    """Request model for AI cost analysis"""
    job_title: str
    job_type: str
    hours_on_site: float
    labour_cost: float
    plant_cost: float
    materials_cost: float
    total_cost: float
    operative_names: list[str]
    notes: Optional[str] = None


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to get current authenticated user"""
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        user_id: str = payload.get("user_id")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise credentials_exception
    
    return user


@router.get("/operatives")
async def get_operatives(current_user: Annotated[dict, Depends(get_current_user)]):
    """Get all operatives with specific fields"""
    db = get_db()
    operatives = []
    async for user in db.users.find({"role": UserRole.operative}):
        operatives.append({
            "id": str(user["_id"]),
            "name": user["name"],
            "email": user["email"],
            "operative_type": user.get("operative_type"),
            "pay_rate": user.get("pay_rate")
        })
    
    return operatives


@router.post("/jobs")
async def create_job(
    job: JobCreate,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Create a new job"""
    db = get_db()
    
    job_doc = {
        "title": job.title,
        "location": job.location,
        "job_type": job.job_type,
        "description": job.description,
        "assigned_operatives": job.assigned_operatives,
        "status": "not_started",
        "created_at": datetime.utcnow()
    }
    
    result = await db.jobs.insert_one(job_doc)
    job_doc["_id"] = result.inserted_id
    
    return {
        "id": str(result.inserted_id),
        "message": "Job created successfully"
    }


@router.get("/jobs", response_model=list[JobResponse])
async def get_jobs(current_user: Annotated[dict, Depends(get_current_user)]):
    """Get all jobs with operative names resolved"""
    db = get_db()
    
    jobs = []
    async for job in db.jobs.find():
        # Resolve operative IDs to operative objects with id and name
        assigned_operatives = []
        for operative_id in job.get("assigned_operatives", []):
            try:
                operative = await db.users.find_one({"_id": ObjectId(operative_id)})
                if operative:
                    assigned_operatives.append({
                        "id": str(operative["_id"]),
                        "name": operative["name"]
                    })
            except Exception:
                pass
        
        jobs.append(JobResponse(
            id=str(job["_id"]),
            title=job["title"],
            location=job["location"],
            job_type=job["job_type"],
            description=job.get("description"),
            status=job["status"],
            assigned_operatives=assigned_operatives,
            created_at=job["created_at"]
        ))
    
    return jobs


@router.put("/operatives/{user_id}/pay")
async def update_operative_pay(
    user_id: str,
    pay_data: UpdatePay,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Update operative's pay rate"""
    db = get_db()
    
    try:
        obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    result = await db.users.update_one(
        {"_id": obj_id},
        {"$set": {"pay_rate": pay_data.pay_rate}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "message": "Pay rate updated successfully",
        "pay_rate": pay_data.pay_rate
    }


@router.put("/jobs/{job_id}")
async def update_job(
    job_id: str,
    job_data: JobUpdate,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Update an existing job"""
    db = get_db()
    
    try:
        obj_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    update_doc = {
        "title": job_data.title,
        "location": job_data.location,
        "job_type": job_data.job_type,
        "assigned_operatives": job_data.assigned_operatives
    }
    
    if job_data.description is not None:
        update_doc["description"] = job_data.description
    
    result = await db.jobs.update_one(
        {"_id": obj_id},
        {"$set": update_doc}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "message": "Job updated successfully",
        "job_id": job_id
    }


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Delete a job"""
    db = get_db()
    
    try:
        obj_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    result = await db.jobs.delete_one({"_id": obj_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "message": "Job deleted successfully"
    }


@router.get("/operative/jobs")
async def get_operative_jobs(current_user: Annotated[dict, Depends(get_current_user)]):
    """Get jobs assigned to current operative"""
    db = get_db()
    current_user_id = str(current_user["_id"])
    
    jobs = []
    async for job in db.jobs.find({"assigned_operatives": current_user_id}):
        # Resolve operative IDs to operative objects with id and name
        assigned_operatives = []
        for operative_id in job.get("assigned_operatives", []):
            try:
                operative = await db.users.find_one({"_id": ObjectId(operative_id)})
                if operative:
                    assigned_operatives.append({
                        "id": str(operative["_id"]),
                        "name": operative["name"]
                    })
            except Exception:
                pass
        
        # Fetch job log if exists
        job_log = await db.job_logs.find_one({"job_id": str(job["_id"])})

        if job_log:
            job_log["_id"] = str(job_log["_id"])
            # Convert datetime objects to strings for frontend
            if "arrival_time" in job_log and job_log["arrival_time"]:
                job_log["arrival_time"] = job_log["arrival_time"].isoformat() if hasattr(job_log["arrival_time"], 'isoformat') else str(job_log["arrival_time"])
            if "departure_time" in job_log and job_log["departure_time"]:
                job_log["departure_time"] = job_log["departure_time"].isoformat() if hasattr(job_log["departure_time"], 'isoformat') else str(job_log["departure_time"])
            # Serialize vehicle arrival times
            if "vehicles" in job_log:
                for vehicle in job_log["vehicles"]:
                    if "arrival_time" in vehicle and vehicle["arrival_time"]:
                        vehicle["arrival_time"] = vehicle["arrival_time"] if isinstance(vehicle["arrival_time"], str) else str(vehicle["arrival_time"])

        jobs.append({
            "id": str(job["_id"]),
            "title": job["title"],
            "location": job["location"],
            "job_type": job["job_type"],
            "description": job.get("description"),
            "status": job["status"],
            "assigned_operatives": assigned_operatives,
            "log": job_log if job_log else None
        })
    
    return jobs


@router.post("/logs/start/{job_id}")
async def start_job_log(
    job_id: str,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Create a new job log"""
    db = get_db()
    operative_id = str(current_user["_id"])
    
    try:
        obj_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    # Check if log already exists for this job and operative
    existing_log = await db.job_logs.find_one({
        "job_id": job_id,
        "operative_id": operative_id
    })
    
    if existing_log:
        return {
            "message": "Log already exists for this job",
            "log_id": str(existing_log["_id"])
        }
    
    # Create new job log
    job_log = {
        "job_id": job_id,
        "operative_id": operative_id,
        "arrival_time": datetime.utcnow(),
        "is_complete": False,
        "vehicles": [],
        "plant_items": [],
        "materials": []
    }
    
    result = await db.job_logs.insert_one(job_log)
    
    # Update job status to in_progress
    await db.jobs.update_one(
        {"_id": obj_id},
        {"$set": {"status": "in_progress"}}
    )
    
    return {
        "message": "Job log created successfully",
        "log_id": str(result.inserted_id)
    }


@router.put("/logs/update/{job_id}")
async def update_job_log(
    job_id: str,
    log_data: JobLogUpdate,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Update existing job log"""
    db = get_db()
    operative_id = str(current_user["_id"])
    
    # Find existing log
    job_log = await db.job_logs.find_one({
        "job_id": job_id,
        "operative_id": operative_id
    })
    
    if not job_log:
        raise HTTPException(status_code=404, detail="Job log not found")
    
    if job_log.get("is_complete", False):
        raise HTTPException(status_code=400, detail="Job already completed")
    
    # Update log
    update_doc = {
        "vehicles": [v.dict() for v in log_data.vehicles],
        "plant_items": [p.dict() for p in log_data.plant_items],
        "materials": [m.dict() for m in log_data.materials]
    }
    
    if log_data.notes is not None:
        update_doc["notes"] = log_data.notes
    
    if log_data.logout_time is not None:
        update_doc["logout_time"] = log_data.logout_time
    
    await db.job_logs.update_one(
        {"_id": job_log["_id"]},
        {"$set": update_doc}
    )
    
    return {
        "message": "Job log updated successfully"
    }


@router.put("/logs/complete/{job_id}")
async def complete_job_log(
    job_id: str,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Complete a job log"""
    db = get_db()
    operative_id = str(current_user["_id"])
    
    # Find existing log
    job_log = await db.job_logs.find_one({
        "job_id": job_id,
        "operative_id": operative_id
    })
    
    if not job_log:
        raise HTTPException(status_code=404, detail="Job log not found")
    # Get arrival_time
    arrival_time = job_log["arrival_time"]
    if isinstance(arrival_time, str):
        arrival_time = datetime.fromisoformat(
            arrival_time.replace('Z', '+00:00')
        ).replace(tzinfo=None)

    # Get departure_time from logout_time
    logout_time_raw = job_log.get("logout_time")
    if logout_time_raw:
        if isinstance(logout_time_raw, str):
            departure_time = datetime.fromisoformat(
                logout_time_raw.replace('Z', '+00:00')
            ).replace(tzinfo=None)
            if departure_time < arrival_time:
                departure_time = departure_time.replace(
                    year=arrival_time.year,
                    month=arrival_time.month,
                    day=arrival_time.day
                )
            if departure_time < arrival_time:
                departure_time = datetime.utcnow()
        else:
            departure_time = logout_time_raw
    else:
        departure_time = datetime.utcnow()

    hours_on_site = round(
        (departure_time - arrival_time).total_seconds() / 3600, 2
    )
    # Get user's pay rate
    user = await db.users.find_one({"_id": current_user["_id"]})
    pay_rate = user.get("pay_rate", 0.0)
    labour_cost = round(hours_on_site * pay_rate, 2)
    import pdb;pdb.set_trace()
    # Update job log
    update_doc = {
        "departure_time": departure_time,
        "is_complete": True,
        "hours_on_site": hours_on_site,
        "labour_cost": labour_cost
    }
    
    await db.job_logs.update_one(
        {"_id": job_log["_id"]},
        {"$set": update_doc}
    )
    
    # Update job status to completed
    try:
        job_obj_id = ObjectId(job_id)
        await db.jobs.update_one(
            {"_id": job_obj_id},
            {"$set": {"status": "completed"}}
        )
    except Exception:
        pass
    
    return {
        "message": "Job log completed successfully",
        "hours_on_site": hours_on_site,
        "labour_cost": labour_cost
    }


@router.post("/resources")
async def create_resource(
    resource: ResourceCreate,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    # import pdb;pdb.set_trace()

    """Create a new resource item"""
    db = get_db()
    resource_doc = {
        "name": resource.name,
        "category": resource.category,
        "price_per_unit": resource.price_per_unit,
        "unit_label": resource.unit_label,
        "created_at": datetime.utcnow()
    }
    
    result = await db.resources.insert_one(resource_doc)
    
    return {
        "message": "Resource created successfully",
        "id": str(result.inserted_id)
    }


@router.get("/resources")
async def get_resources(current_user: Annotated[dict, Depends(get_current_user)]):
    """Get all resources"""
    db = get_db()
    
    resources = []
    async for resource in db.resources.find():
        resources.append({
            "id": str(resource["_id"]),
            "name": resource["name"],
            "category": resource["category"],
            "price_per_unit": resource["price_per_unit"],
            "unit_label": resource["unit_label"]
        })
    
    return resources


@router.put("/resources/{resource_id}")
async def update_resource(
    resource_id: str,
    resource: ResourceCreate,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    # import pdb;pdb.set_trace()
    """Update existing resource"""
    db = get_db()
    
    try:
        obj_id = ObjectId(resource_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid resource ID format")
    
    update_doc = {
        "name": resource.name,
        "category": resource.category,
        "price_per_unit": resource.price_per_unit,
        "unit_label": resource.unit_label
    }
    
    result = await db.resources.update_one(
        {"_id": obj_id},
        {"$set": update_doc}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    return {
        "message": "Resource updated successfully"
    }


@router.delete("/resources/{resource_id}")
async def delete_resource(
    resource_id: str,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Delete a resource"""
    db = get_db()
    
    try:
        obj_id = ObjectId(resource_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid resource ID format")
    
    result = await db.resources.delete_one({"_id": obj_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    return {
        "message": "Resource deleted successfully"
    }


@router.get("/qs/jobs/completed")
async def get_completed_jobs(current_user: Annotated[dict, Depends(get_current_user)]):
    """Get all completed jobs with cost breakdown"""
    db = get_db()
    
    completed_jobs = []
    async for job in db.jobs.find({"status": "completed"}):
        # Fetch job log
        job_log = await db.job_logs.find_one({"job_id": str(job["_id"])})
        
        if not job_log:
            continue
        
        # Resolve assigned_operatives with pay_rate
        assigned_operatives = []
        for operative_id in job.get("assigned_operatives", []):
            try:
                operative = await db.users.find_one({"_id": ObjectId(operative_id)})
                if operative:
                    assigned_operatives.append({
                        "id": str(operative["_id"]),
                        "name": operative["name"],
                        "pay_rate": operative.get("pay_rate", 0.0)
                    })
            except Exception:
                pass
        
        # Process plant items with pricing
        plant_items_with_costs = []
        plant_cost = 0.0
        for item in job_log.get("plant_items", []):
            resource = await db.resources.find_one({"name": item["item_name"]})
            if resource:
                price_per_unit = resource.get("price_per_unit", 0.0)
                subtotal = item["quantity"] * price_per_unit
                plant_cost += subtotal
                plant_items_with_costs.append({
                    "item_name": item["item_name"],
                    "quantity": item["quantity"],
                    "price_per_unit": price_per_unit,
                    "subtotal": subtotal
                })
            else:
                plant_items_with_costs.append({
                    "item_name": item["item_name"],
                    "quantity": item["quantity"],
                    "price_per_unit": 0.0,
                    "subtotal": 0.0
                })
        
        # Process materials with pricing
        materials_with_costs = []
        materials_cost = 0.0
        for item in job_log.get("materials", []):
            resource = await db.resources.find_one({"name": item["item_name"]})
            if resource:
                price_per_unit = resource.get("price_per_unit", 0.0)
                subtotal = item["quantity"] * price_per_unit
                materials_cost += subtotal
                materials_with_costs.append({
                    "item_name": item["item_name"],
                    "quantity": item["quantity"],
                    "price_per_unit": price_per_unit,
                    "subtotal": subtotal
                })
            else:
                materials_with_costs.append({
                    "item_name": item["item_name"],
                    "quantity": item["quantity"],
                    "price_per_unit": 0.0,
                    "subtotal": 0.0
                })
        
        # Calculate total cost
        labour_cost = job_log.get("labour_cost", 0.0)
        total_cost = labour_cost + plant_cost + materials_cost
        
        completed_jobs.append({
            "id": str(job["_id"]),
            "title": job["title"],
            "location": job["location"],
            "job_type": job["job_type"],
            "description": job.get("description"),
            "assigned_operatives": assigned_operatives,
            "log": {
                "arrival_time": job_log.get("arrival_time"),
                "departure_time": job_log.get("departure_time"),
                "logout_time": job_log.get("logout_time"),
                "hours_on_site": job_log.get("hours_on_site"),
                "labour_cost": labour_cost,
                "vehicles": job_log.get("vehicles", []),
                "plant_items": plant_items_with_costs,
                "materials": materials_with_costs,
                "notes": job_log.get("notes"),
                "plant_cost": round(plant_cost, 2),
                "materials_cost": round(materials_cost, 2),
                "total_cost": round(total_cost, 2)
            }
        })
    
    return completed_jobs


@router.get("/users/all")
async def get_all_users(current_user: Annotated[dict, Depends(get_current_user)]):
    """Get all users"""
    db = get_db()
    
    users = []
    async for user in db.users.find():
        users.append({
            "id": str(user["_id"]),
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "operative_type": user.get("operative_type"),
            "pay_rate": user.get("pay_rate")
        })
    
    return users


@router.post("/qs/jobs/{job_id}/ai-analysis")
async def ai_cost_analysis(
    job_id: str,
    request: AIAnalysisRequest,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Analyze job costs using Groq AI"""
    # import pdb;pdb.set_trace()
    if not GROQ_API_KEY or not GROQ_BASE_URL or not GROQ_MODEL:
        raise HTTPException(status_code=500, detail="Groq API configuration missing")
    
    async with httpx.AsyncClient() as client:
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a cost analysis assistant for a UK streetlighting maintenance company called McCann. Analyse job cost data and provide a brief 2-sentence assessment. Flag anything unusual such as high hours for the job type, zero costs where costs are expected, or significant cost imbalances. Be concise and professional."
                },
                {
                    "role": "user",
                    "content": request.json()
                }
            ],
            "max_tokens": 150
        }
        
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            response = await client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail="Groq API request failed")
            
            result = response.json()
            analysis_text = result["choices"][0]["message"]["content"]
            
            return {"analysis": analysis_text}
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"API request error: {str(e)}")
