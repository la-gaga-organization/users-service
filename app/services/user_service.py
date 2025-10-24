from __future__ import annotations

import json
from enum import Enum
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.http_client import OrientatiException
from app.services.broker import AsyncBrokerSingleton
from app.core.logging import get_logger

logger = get_logger(__name__)

RABBIT_DELETE_TYPE = "DELETE"
RABBIT_UPDATE_TYPE = "UPDATE"
RABBIT_CREATE_TYPE = "CREATE"

class UserCreateErrorType(Enum):
    INVALID_EMAIL = "invalid_email"
    USERNAME_TAKEN = "username_taken"
    EMAIL_TAKEN = "email_taken"
    INVALID_PASSWORD = "invalid_password"

class UserCreateError(OrientatiException):
    def __init__(self, message: str,error_type:str = "default_error"):
        super().__init__("Bad Request", 400, {
            "message": message,
            "type": error_type
        }, "/users/create")

def list_users(db: Session, limit: int = 50, offset: int = 0) -> Iterable[User]:
    try:
        stmt = select(User).limit(limit).offset(offset)
        return db.execute(stmt).scalars().all()
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url="users/list",
        )


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


async def create_user(db: Session, payload: UserCreate) -> User:
    try:
        existing_user = db.query(User).filter_by(email=payload.email).first()
        if existing_user:
            raise UserCreateError(
                message="Email already in use",
                error_type=UserCreateErrorType.EMAIL_TAKEN.value,
            )
        
        if not payload.email or "@" not in payload.email:
            raise UserCreateError(
                message="Invalid email format",
                error_type=UserCreateErrorType.INVALID_EMAIL.value,
            )

        if not payload.username or len(payload.username) < 3:
            raise UserCreateError(
                message="Invalid username",
                error_type=UserCreateErrorType.USERNAME_TAKEN.value,
            )

        user = User(**payload.model_dump())
        db.add(user)
        db.commit()
        db.refresh(user)
        await update_services(user, RABBIT_CREATE_TYPE)
        return user
    except UserCreateError as e:
        raise e
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url="users/create",
        )


async def update_user(db: Session, user_id: int, payload: UserUpdate) -> User | None:
    try:
        user = db.get(User, user_id)
        if not user:
            raise OrientatiException(
                status_code=404,
                message="Not Found",
                details={"message": "User not found"},
                url=f"users/{user_id}"
            )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        db.commit()
        db.refresh(user)
        await update_services(user, RABBIT_UPDATE_TYPE)
        return user
    except OrientatiException as e:
        raise e
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url=f"users/{user_id}",
        )

async def change_user_password(db: Session, user_id: int, old_password: str, new_password: str) -> bool:
    try:
        user = db.get(User, user_id)
        if not user or user.hashed_password != old_password:
            return False
        user.hashed_password = new_password
        db.commit()
        db.refresh(user)
        await update_services(user, RABBIT_UPDATE_TYPE)
        return True
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url=f"users/{user_id}/change_password",
        )


async def delete_user(db: Session, user_id: int) -> bool:
    try:
        user = db.get(User, user_id)
        if not user:
            return False
        db.delete(user)
        db.commit()
        await update_services(user, RABBIT_DELETE_TYPE)
        return True
    except Exception as e:
        raise OrientatiException(
            exc=e,
            url=f"users/{user_id}/delete",
        )

async def update_services(user: User, operation: str):
    try:
        broker_instance = AsyncBrokerSingleton()
        connected = await broker_instance.connect()
        if connected:
            message = {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "name": user.name,
                "surname": user.surname,
                "hashed_password": user.hashed_password,
                "created_at": str(user.created_at),
                "updated_at": str(user.updated_at)
            } if operation != RABBIT_DELETE_TYPE else {"id": user.id}
            await broker_instance.publish_message("users", operation, message)
        else:
            logger.warning("Could not connect to broker.")
    except Exception as e:
        logger.error(f"Error updating services for user {user.id}. Operation: {operation}: {e}")
        raise e