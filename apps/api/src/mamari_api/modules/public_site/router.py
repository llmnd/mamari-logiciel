import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from mamari_api.core.config import get_settings
from mamari_api.modules.identity.dependencies import (
    CurrentMembership,
    SessionDep,
    require_roles,
)
from mamari_api.modules.identity.models import Organization
from mamari_api.modules.public_site.models import ContactInquiry, NewsletterSubscriber
from mamari_api.modules.public_site.schemas import (
    ContactInquiryRequest,
    ContactInquiryResponse,
    ContactInquiryStatusRequest,
    NewsletterSubscribeRequest,
    NewsletterSubscribeResponse,
    NewsletterSubscriberResponse,
    NewsletterUnsubscribeRequest,
    PublicInboxResponse,
)

router = APIRouter(prefix="/public")
CanManagePublicInboxDep = Annotated[
    CurrentMembership,
    Depends(require_roles("owner", "admin", "manager")),
]


async def _public_organization_id(session: SessionDep) -> uuid.UUID:
    organization_id = await session.scalar(
        select(Organization.id).where(
            Organization.slug == get_settings().public_store_slug,
            Organization.is_active.is_(True),
        )
    )
    if organization_id is None:
        raise HTTPException(status_code=404, detail="Le site Mamari est indisponible.")
    return organization_id


@router.post(
    "/newsletter",
    response_model=NewsletterSubscribeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def subscribe_to_newsletter(
    data: NewsletterSubscribeRequest,
    session: SessionDep,
) -> NewsletterSubscribeResponse:
    organization_id = await _public_organization_id(session)
    if data.website:
        return NewsletterSubscribeResponse(subscribed=True)
    email = str(data.email).strip().lower()
    existing = await session.scalar(
        select(NewsletterSubscriber).where(
            NewsletterSubscriber.organization_id == organization_id,
            NewsletterSubscriber.email == email,
        )
    )
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            existing.consented_at = datetime.now(UTC)
            await session.commit()
            return NewsletterSubscribeResponse(
                subscribed=True,
                unsubscribe_token=existing.unsubscribe_token,
            )
        return NewsletterSubscribeResponse(subscribed=True, already_subscribed=True)

    subscriber = NewsletterSubscriber(
        organization_id=organization_id,
        email=email,
        consented_at=datetime.now(UTC),
    )
    session.add(subscriber)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(NewsletterSubscriber).where(
                NewsletterSubscriber.organization_id == organization_id,
                NewsletterSubscriber.email == email,
                NewsletterSubscriber.is_active.is_(True),
            )
        )
        if existing is None:
            raise
        return NewsletterSubscribeResponse(subscribed=True, already_subscribed=True)
    await session.refresh(subscriber)
    return NewsletterSubscribeResponse(
        subscribed=True,
        unsubscribe_token=subscriber.unsubscribe_token,
    )


@router.post("/newsletter/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe_from_newsletter(
    data: NewsletterUnsubscribeRequest,
    session: SessionDep,
) -> None:
    subscriber = await session.scalar(
        select(NewsletterSubscriber).where(
            NewsletterSubscriber.unsubscribe_token == data.token,
            NewsletterSubscriber.is_active.is_(True),
        )
    )
    if subscriber is None:
        raise HTTPException(status_code=404, detail="Inscription active introuvable.")
    subscriber.is_active = False
    await session.commit()


@router.post(
    "/contact",
    response_model=ContactInquiryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_contact_inquiry(
    data: ContactInquiryRequest,
    session: SessionDep,
) -> ContactInquiryResponse:
    organization_id = await _public_organization_id(session)
    if data.website:
        return ContactInquiryResponse(
            id=uuid.uuid4(),
            full_name=data.full_name,
            email=data.email,
            subject=data.subject,
            message="",
            status="new",
            created_at=datetime.now(UTC),
        )
    inquiry = ContactInquiry(
        organization_id=organization_id,
        full_name=data.full_name,
        email=str(data.email).strip().lower(),
        subject=data.subject,
        message=data.message,
        status="new",
        consented_at=datetime.now(UTC),
    )
    session.add(inquiry)
    await session.commit()
    await session.refresh(inquiry)
    return ContactInquiryResponse.model_validate(inquiry)


@router.get("/inbox", response_model=PublicInboxResponse)
async def read_public_inbox(
    session: SessionDep,
    context: CanManagePublicInboxDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PublicInboxResponse:
    organization_id = context.organization.id
    inquiry_total = await session.scalar(
        select(func.count()).select_from(ContactInquiry).where(
            ContactInquiry.organization_id == organization_id
        )
    )
    subscriber_total = await session.scalar(
        select(func.count()).select_from(NewsletterSubscriber).where(
            NewsletterSubscriber.organization_id == organization_id,
            NewsletterSubscriber.is_active.is_(True),
        )
    )
    inquiries = await session.scalars(
        select(ContactInquiry)
        .where(ContactInquiry.organization_id == organization_id)
        .order_by(ContactInquiry.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    subscribers = await session.scalars(
        select(NewsletterSubscriber)
        .where(
            NewsletterSubscriber.organization_id == organization_id,
            NewsletterSubscriber.is_active.is_(True),
        )
        .order_by(NewsletterSubscriber.created_at.desc())
        .limit(500)
    )
    return PublicInboxResponse(
        inquiries=[ContactInquiryResponse.model_validate(item) for item in inquiries],
        subscribers=[
            NewsletterSubscriberResponse.model_validate(item) for item in subscribers
        ],
        inquiry_total=inquiry_total or 0,
        subscriber_total=subscriber_total or 0,
    )


@router.patch("/inbox/{inquiry_id}", response_model=ContactInquiryResponse)
async def update_inquiry_status(
    inquiry_id: uuid.UUID,
    data: ContactInquiryStatusRequest,
    session: SessionDep,
    context: CanManagePublicInboxDep,
) -> ContactInquiryResponse:
    inquiry = await session.scalar(
        select(ContactInquiry).where(
            ContactInquiry.id == inquiry_id,
            ContactInquiry.organization_id == context.organization.id,
        )
    )
    if inquiry is None:
        raise HTTPException(status_code=404, detail="Message introuvable.")
    inquiry.status = data.status
    await session.commit()
    await session.refresh(inquiry)
    return ContactInquiryResponse.model_validate(inquiry)
