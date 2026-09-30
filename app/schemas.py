from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
class RegisterRequest(BaseModel): email:EmailStr; name:str=Field(min_length=2,max_length=120); password:str=Field(min_length=8,max_length=128)
class LoginRequest(BaseModel): email:EmailStr; password:str=Field(min_length=1,max_length=128)
class UserResponse(BaseModel): model_config=ConfigDict(from_attributes=True); id:str; email:EmailStr; name:str
class AudienceCreate(BaseModel): name:str=Field(min_length=1,max_length=120)
class AudienceResponse(BaseModel): model_config=ConfigDict(from_attributes=True); id:str; name:str; created_at:datetime; contact_count:int=0
class ContactCreate(BaseModel): email:EmailStr; first_name:str|None=Field(default=None,max_length=80); last_name:str|None=Field(default=None,max_length=80)
class ContactResponse(BaseModel): model_config=ConfigDict(from_attributes=True); id:str; email:EmailStr; first_name:str|None; last_name:str|None; unsubscribed_at:datetime|None; created_at:datetime
class CampaignCreate(BaseModel): name:str=Field(min_length=1,max_length=140); audience_id:str; subject:str=Field(min_length=1,max_length=200); body_html:str=Field(min_length=1); scheduled_at:datetime|None=None
class CampaignUpdate(BaseModel): name:str|None=Field(default=None,min_length=1,max_length=140); subject:str|None=Field(default=None,min_length=1,max_length=200); body_html:str|None=Field(default=None,min_length=1); audience_id:str|None=None; scheduled_at:datetime|None=None
class CampaignResponse(BaseModel): model_config=ConfigDict(from_attributes=True); id:str; name:str; audience_id:str; subject:str; body_html:str; status:str; scheduled_at:datetime|None; created_at:datetime; updated_at:datetime; audience_name:str|None=None
class DeliverySummary(BaseModel): total:int; queued:int; sent:int; failed:int; opened:int; clicked:int
class CampaignReport(BaseModel): campaign:CampaignResponse; latest_run_status:str|None; summary:DeliverySummary
class DashboardSummary(BaseModel): audience_contacts:int; audiences:int; active_campaigns:int; scheduled_campaigns:int; sent_deliveries:int
