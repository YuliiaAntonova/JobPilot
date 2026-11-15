"""Registration, login, current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from job_application.utils.auth import create_access_token, hash_password, verify_password
from job_application.models.db import get_db
from job_application.repositories import users as db_users
from job_application.routers.deps import get_current_user
from job_application.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@router.post("/register", response_model=TokenOut)
def register(body: AuthBody, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db_users.get_user_by_email(db, email):
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    user = db_users.create_user(db, email, hash_password(body.password))
    token = create_access_token(user.id, user.email)
    return TokenOut(access_token=token, user=UserOut(id=user.id, email=user.email))


@router.post("/login", response_model=TokenOut)
def login(body: AuthBody, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db_users.get_user_by_email(db, email)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user.id, user.email)
    return TokenOut(access_token=token, user=UserOut(id=user.id, email=user.email))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, email=user.email)
