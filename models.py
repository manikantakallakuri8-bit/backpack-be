from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, EmailStr
from datetime import datetime


class UserRole(str, Enum):
    operative = "operative"
    supervisor = "supervisor"
    qs = "qs"


class OperativeType(str, Enum):
    street_lighting = "street_lighting"
    civils = "civils"
    hiab = "hiab"
    electrician = "electrician"
    icp_jointer = "icp_jointer"


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole
    operative_type: Optional[OperativeType] = None

    class Config:
        use_enum_values = True


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    name: str
    user_id: str


class JobCreate(BaseModel):
    title: str
    location: str
    job_type: str
    description: Optional[str] = None
    assigned_operatives: List[str] = []

class OperativeResponse(BaseModel):
    id: str
    name: str
    
class JobResponse(BaseModel):
    id: str
    title: str
    location: str
    job_type: str
    description: Optional[str] = None
    status: str
    assigned_operatives: List[OperativeResponse]
    created_at: datetime


class UpdatePay(BaseModel):
    pay_rate: float


class JobUpdate(BaseModel):
    title: str
    location: str
    job_type: str
    description: Optional[str] = None
    assigned_operatives: List[str]


class Vehicle(BaseModel):
    vehicle_type: str
    registration: str
    arrival_time: str


class PlantItem(BaseModel):
    item_name: str
    quantity: int


class MaterialItem(BaseModel):
    item_name: str
    quantity: float


class JobLogUpdate(BaseModel):
    vehicles: List[Vehicle] = []
    plant_items: List[PlantItem] = []
    materials: List[MaterialItem] = []
    notes: Optional[str] = None
    logout_time: Optional[str] = None


class ResourceCreate(BaseModel):
    name: str
    category: str
    price_per_unit: float
    unit_label: str

class AIAnalysisRequest(BaseModel):
    job_title: str
    job_type: str
    hours_on_site: float
    labour_cost: float
    plant_cost: float
    materials_cost: float
    total_cost: float
    operative_names: List[str]
    notes: Optional[str] = None