import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from mamari_api.core.config import get_settings
from mamari_api.modules.identity.dependencies import (
    CurrentMembership,
    CurrentUserDep,
    OptionalCurrentUserDep,
    SessionDep,
    get_current_membership,
)
from mamari_api.modules.identity.models import Membership, Organization, User
from mamari_api.modules.identity.schemas import (
    ChangePasswordRequest,
    CustomerRegistrationRequest,
    LoginRequest,
    MembershipResponse,
    MessageResponse,
    PublicAuthStatusResponse,
    UpdateCurrentUserRequest,
    UserResponse,
)
from mamari_api.modules.identity.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from mamari_api.modules.identity.service import authenticate_user
from mamari_api.modules.sales.models import Customer

router = APIRouter(prefix="/auth")
CurrentMembershipDep = Annotated[CurrentMembership, Depends(get_current_membership)]


async def user_response(session: SessionDep, user: User) -> UserResponse:
    result = await session.execute(
        select(Membership, Organization)
        .join(Organization, Membership.organization_id == Organization.id)
        .where(
            Membership.user_id == user.id,
            Membership.is_active.is_(True),
            Organization.is_active.is_(True),
        )
        .order_by(Organization.name)
    )
    rows = result.all()
    memberships = [
        MembershipResponse(
            organization_id=organization.id,
            organization_name=organization.name,
            organization_slug=organization.slug,
            role=membership.role,
        )
        for membership, organization in rows
    ]
    customer_account = await session.scalar(
        select(Customer.id).where(Customer.user_id == user.id).limit(1)
    )
    return UserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        phone=rows[0][0].phone if rows else None,
        memberships=memberships,
        customer_account=customer_account is not None,
    )


def set_session_cookie(response: Response, user_id: uuid.UUID) -> None:
    token, lifetime = create_access_token(user_id)
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=lifetime,
        httponly=True,
        secure=get_settings().app_env == "production",
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=UserResponse, summary="Ouvrir une session")
async def login(data: LoginRequest, response: Response, session: SessionDep) -> UserResponse:
    user = await authenticate_user(session, data.username, data.password)
    authenticated_user = await user_response(session, user)
    if not authenticated_user.memberships and not authenticated_user.customer_account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Aucune organisation active n'est associée à ce compte.",
        )
    set_session_cookie(response, user.id)
    return authenticated_user


@router.post(
    "/customer/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un compte client",
)
async def register_customer(
    data: CustomerRegistrationRequest,
    response: Response,
    session: SessionDep,
) -> UserResponse:
    organization = await session.scalar(
        select(Organization).where(
            Organization.slug == get_settings().public_store_slug,
            Organization.is_active.is_(True),
        )
    )
    if organization is None:
        raise HTTPException(status_code=404, detail="La boutique Mamari est indisponible.")

    email = str(data.email).casefold()
    existing_user = await session.scalar(
        select(User.id).where(func.lower(User.email) == email)
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un compte utilise déjà cette adresse e-mail. Connectez-vous plutôt.",
        )

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        username=f"client-{user_id.hex[:20]}",
        email=email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
    )
    customer = Customer(
        organization_id=organization.id,
        user_id=user.id,
        customer_type="individual",
        name=data.full_name,
        phone=data.phone,
        email=email,
    )
    session.add_all([user, customer])
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint not in {"users_email_key", "uq_users_email", "uq_users_username"} and not (
            "UNIQUE constraint failed: users.email" in str(error.orig)
            or "UNIQUE constraint failed: users.username" in str(error.orig)
        ):
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un compte utilise déjà cette adresse e-mail. Connectez-vous plutôt.",
        ) from None
    set_session_cookie(response, user.id)
    return await user_response(session, user)


@router.post("/logout", response_model=MessageResponse, summary="Fermer la session")
async def logout(response: Response) -> MessageResponse:
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=get_settings().app_env == "production",
        samesite="lax",
        path="/",
    )
    return MessageResponse(message="Session fermée.")


@router.get("/me", response_model=UserResponse, summary="Consulter le compte connecté")
async def read_current_user(session: SessionDep, user: CurrentUserDep) -> UserResponse:
    return await user_response(session, user)


@router.get("/public-status", response_model=PublicAuthStatusResponse)
async def read_public_auth_status(
    session: SessionDep,
    user: OptionalCurrentUserDep,
) -> PublicAuthStatusResponse:
    if user is None:
        return PublicAuthStatusResponse(customer_account=False)
    customer_account = await session.scalar(
        select(Customer.id)
        .join(Organization, Organization.id == Customer.organization_id)
        .where(
            Customer.user_id == user.id,
            Organization.slug == get_settings().public_store_slug,
            Organization.is_active.is_(True),
        )
        .limit(1)
    )
    return PublicAuthStatusResponse(customer_account=customer_account is not None)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Modifier le profil du compte connecté",
)
async def update_current_user(
    data: UpdateCurrentUserRequest,
    session: SessionDep,
    context: CurrentMembershipDep,
) -> UserResponse:
    changes = data.model_dump(exclude_unset=True)
    if "full_name" in changes:
        context.user.full_name = changes["full_name"]
    if "phone" in changes:
        context.membership.phone = changes["phone"]
    await session.commit()
    return await user_response(session, context.user)


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Modifier le mot de passe du compte connecté",
)
async def change_password(
    data: ChangePasswordRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> MessageResponse:
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le mot de passe actuel est incorrect.",
        )
    if verify_password(data.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choisissez un mot de passe différent de l’actuel.",
        )
    user.password_hash = hash_password(data.new_password)
    await session.commit()
    return MessageResponse(message="Votre mot de passe a été modifié.")
