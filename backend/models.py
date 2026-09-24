"""Pydantic input models for the ShowUpAI API."""
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

class BlogPostIn(BaseModel):
    slug: str
    title: str
    excerpt: Optional[str] = ""
    content: Optional[str] = ""
    meta_description: Optional[str] = ""
    meta_keywords: Optional[str] = ""
    published: Optional[bool] = False
    reading_time: Optional[int] = 5
    seo_title: Optional[str] = ""
    seo_description: Optional[str] = ""
    seo_keywords: Optional[str] = ""
    og_title: Optional[str] = ""
    og_description: Optional[str] = ""
    og_image: Optional[str] = ""
    twitter_card: Optional[str] = "summary_large_image"
    twitter_title: Optional[str] = ""
    twitter_description: Optional[str] = ""
    twitter_image: Optional[str] = ""
    faq_items: Optional[List[Dict]] = []
    common_questions: Optional[List[str]] = []
    entities: Optional[List[str]] = []
    related_topics: Optional[List[str]] = []
    answer_focus: Optional[str] = ""
    authority_signals: Optional[List[str]] = []
    problem_statement: Optional[str] = ""
    solution_framework: Optional[str] = ""
    actionable_takeaways: Optional[List[str]] = []
    case_studies: Optional[List[Dict]] = []

class BlogPostPatch(BaseModel):
    title: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    published: Optional[bool] = None
    reading_time: Optional[int] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_keywords: Optional[str] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    twitter_card: Optional[str] = None
    twitter_title: Optional[str] = None
    twitter_description: Optional[str] = None
    twitter_image: Optional[str] = None
    faq_items: Optional[List[Dict]] = None
    common_questions: Optional[List[str]] = None
    entities: Optional[List[str]] = None
    related_topics: Optional[List[str]] = None
    answer_focus: Optional[str] = None
    authority_signals: Optional[List[str]] = None
    problem_statement: Optional[str] = None
    solution_framework: Optional[str] = None
    actionable_takeaways: Optional[List[str]] = None
    case_studies: Optional[List[Dict]] = None
