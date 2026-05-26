from enum import Enum
from typing import Optional
from pydantic import BaseModel, EmailStr


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
