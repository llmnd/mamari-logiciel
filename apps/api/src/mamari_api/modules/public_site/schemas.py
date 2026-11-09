import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints


class NewsletterSubscribeRequest(BaseModel):
    email: EmailStr
    consent: Literal[True]
    website: Annotated[str, StringConstraints(max_length=200)] = ""


class NewsletterUnsubscribeRequest(BaseModel):
    token: uuid.UUID


class NewsletterSubscribeResponse(BaseModel):
    subscribed: bool
    already_subscribed: bool = False
    unsubscribe_token: uuid.UUID | None = None


class ContactInquiryRequest(BaseModel):
    full_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)
    ]
    email: EmailStr
    subject: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)
    ]
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=10, max_length=5000)
    ]
    consent: Literal[True]
    website: Annotated[str, StringConstraints(max_length=200)] = ""


class ContactInquiryStatusRequest(BaseModel):
    status: Literal["new", "read", "replied"]


class NewsletterSubscriberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_active: bool
    consented_at: datetime
    created_at: datetime


class ContactInquiryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: EmailStr
    subject: str
    message: str
    status: Literal["new", "read", "replied"]
    created_at: datetime


class PublicInboxResponse(BaseModel):
    inquiries: list[ContactInquiryResponse]
    subscribers: list[NewsletterSubscriberResponse]
    inquiry_total: int
    subscriber_total: int
