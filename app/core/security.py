from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from .config import get_settings
_hasher=PasswordHasher(time_cost=2,memory_cost=19456,parallelism=1)
ALGORITHM="HS256"
def hash_password(password:str)->str: return _hasher.hash(password)
def verify_password(password:str,encoded:str)->bool:
    try: return _hasher.verify(encoded,password)
    except VerifyMismatchError: return False
def create_access_token(user_id:str)->str:
    exp=datetime.now(timezone.utc)+timedelta(minutes=get_settings().jwt_expire_minutes)
    return jwt.encode({"sub":user_id,"exp":exp},get_settings().jwt_secret_key,algorithm=ALGORITHM)
def decode_access_token(token:str)->str:
    payload=jwt.decode(token,get_settings().jwt_secret_key,algorithms=[ALGORITHM])
    subject=payload.get("sub")
    if not subject: raise ValueError("missing subject")
    return subject
