from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    email: EmailStr
    name: str
    surname: str


class UserCreate(UserBase):
    hashed_password: str


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    name: str | None = None
    surname: str | None = None


class UserOut(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
