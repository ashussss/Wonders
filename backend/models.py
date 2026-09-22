"""Pydantic input models for the ShowUp.ai API."""
from typing import List, Optional, Dict
from pydantic import BaseModel, EmailStr


class UserSignup(BaseModel):
    email: EmailStr
    password: str
    name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class WebinarIn(BaseModel):
    title: str
    description: str
    speaker: str = ""
    speakers: Optional[str] = ""        # multi-speaker comma separated
    target_audience: str = ""
    starts_at: str  # ISO datetime
    timezone: str = "Europe/London"
    join_link: str = ""
    registration_link: str = ""
    custom_context: Optional[str] = ""  # extra AI instructions for this webinar
    key_topics: Optional[str] = ""      # key topics/outcomes


class WebinarPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    speaker: Optional[str] = None
    speakers: Optional[str] = None
    target_audience: Optional[str] = None
    starts_at: Optional[str] = None
    timezone: Optional[str] = None
    join_link: Optional[str] = None
    registration_link: Optional[str] = None
    status: Optional[str] = None
    custom_context: Optional[str] = None
    key_topics: Optional[str] = None


class RegistrantIn(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    source: str = "form"


class TouchPatch(BaseModel):
    channels: Optional[List[str]] = None
    scheduled_at: Optional[str] = None
    selected_variant: Optional[int] = None
    copy_overrides: Optional[Dict[str, str]] = None
    approval_status: Optional[str] = None  # pending/approved/rejected
    ai_copy: Optional[Dict] = None         # direct ai_copy override (for delete content)


class LeadMagnetPatch(BaseModel):
    edited_content: Optional[str] = None
    approval_status: Optional[str] = None


class SettingsIn(BaseModel):
    email_provider: Optional[str] = None
    brevo_api_key: Optional[str] = None
    brevo_sender_email: Optional[EmailStr] = None
    brevo_sender_name: Optional[str] = None
    mailchimp_api_key: Optional[str] = None
    mailchimp_sender_email: Optional[EmailStr] = None
    mailchimp_sender_name: Optional[str] = None
    sendgrid_api_key: Optional[str] = None
    sendgrid_sender_email: Optional[EmailStr] = None
    sendgrid_sender_name: Optional[str] = None
    buzzai_api_key: Optional[str] = None
    buzzai_email_endpoint: Optional[str] = None
    buzzai_linkedin_endpoint: Optional[str] = None
    buzzai_auth_header_name: Optional[str] = None
    buzzai_auth_header_prefix: Optional[str] = None
    linkedin_marketing_token: Optional[str] = None
    linkedin_events_token: Optional[str] = None
    linkedin_org_urn: Optional[str] = None
    linkedin_provider: Optional[str] = None  # "marketing_api" | "buzzai"
    meta_graph_token: Optional[str] = None
    meta_page_id: Optional[str] = None
    instagram_business_id: Optional[str] = None
    twilio_sid: Optional[str] = None
    twilio_token: Optional[str] = None
    twilio_from: Optional[str] = None
    circle_api_key: Optional[str] = None
    circle_space_id: Optional[str] = None
    default_touches: Optional[Dict[str, bool]] = None
    default_channels: Optional[Dict[str, List[str]]] = None
    per_touch_auto_send: Optional[Dict[str, bool]] = None
    brand_tone: Optional[str] = None          # professional/casual/friendly
    brand_language: Optional[str] = None      # "UK English", "US English" etc
    brand_audience: Optional[str] = None      # global audience description
    brand_banned_phrases: Optional[str] = None # comma separated
    brand_always_include: Optional[str] = None # things to always mention
