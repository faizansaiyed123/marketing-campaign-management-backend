from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .core.config import get_settings
from .core.security import decode_access_token
from .db import get_db
from .models import User
def get_current_user(db:Session=Depends(get_db),session_token:str|None=Cookie(default=None,alias=get_settings().cookie_name)):
    if not session_token: raise HTTPException(401,"Authentication required")
    try: user_id=decode_access_token(session_token)
    except Exception: raise HTTPException(401,"Invalid or expired session")
    user=db.scalar(select(User).where(User.id==user_id))
    if not user: raise HTTPException(401,"User not found")
    return user
