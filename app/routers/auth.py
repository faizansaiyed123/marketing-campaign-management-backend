from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..core.config import get_settings
from ..core.security import create_access_token, hash_password, verify_password
from ..db import get_db
from ..dependencies import get_current_user
from ..models import User
from ..schemas import LoginRequest, RegisterRequest, UserResponse
router=APIRouter(prefix="/api/v1/auth",tags=["auth"])
def set_cookie(response:Response,token:str):
    s=get_settings(); response.set_cookie(s.cookie_name,token,httponly=True,secure=s.cookie_secure,samesite="strict",max_age=s.jwt_expire_minutes*60,path="/")
@router.post("/register",response_model=UserResponse,status_code=201)
def register(payload:RegisterRequest,response:Response,db:Session=Depends(get_db)):
    email=payload.email.lower()
    if db.scalar(select(User).where(User.email==email)): raise HTTPException(409,"Email is already registered")
    user=User(id=str(uuid4()),email=email,name=payload.name.strip(),password_hash=hash_password(payload.password))
    db.add(user); db.commit(); db.refresh(user); set_cookie(response,create_access_token(user.id)); return user
@router.post("/login",response_model=UserResponse)
def login(payload:LoginRequest,response:Response,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==payload.email.lower()))
    if not user or not verify_password(payload.password,user.password_hash): raise HTTPException(401,"Invalid email or password")
    set_cookie(response,create_access_token(user.id)); return user
@router.post("/logout",status_code=204)
def logout(response:Response): response.delete_cookie(get_settings().cookie_name,path="/")
@router.get("/me",response_model=UserResponse)
def me(user=Depends(get_current_user)): return user
