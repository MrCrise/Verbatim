from pydantic import BaseModel, EmailStr, UUID4, Field
from typing import Optional


# --- Токены ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- Пользователи ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72, description="Password (8-72 characters)")
    full_name: str

class UserResponse(BaseModel):
    id: UUID4
    email: EmailStr
    full_name: str
    is_admin: bool

    class Config:
        from_attributes = True
