import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    HttpUrl,
    StringConstraints,
    model_validator,
)

Password = Annotated[str, StringConstraints(min_length=6, max_length=128)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=32)]
Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=32,
        pattern=r"(?i)^[a-z0-9][a-z0-9._-]*$",
    ),
]
LoginIdentifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=320),
]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]


class LoginRequest(BaseModel):
    username: LoginIdentifier
    password: Password


class CustomerRegistrationRequest(BaseModel):
    full_name: FullName
    email: EmailStr
    phone: Phone
    password: Password


class ChangePasswordRequest(BaseModel):
    current_password: Password
    new_password: Password


class UpdateCurrentUserRequest(BaseModel):
    full_name: FullName | None = None
    phone: Phone | None = None

    @model_validator(mode="after")
    def require_update_field(self) -> "UpdateCurrentUserRequest":
        if not self.model_fields_set:
            raise ValueError("Renseignez au moins une information à modifier.")
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("Le nom complet ne peut pas être vide.")
        return self


class CreateUserRequest(BaseModel):
    username: Username
    full_name: FullName
    password: Password
    role: Literal["admin", "manager", "operator", "reader"]
    phone: Phone | None = None


class UpdateOrganizationUserRequest(BaseModel):
    full_name: FullName | None = None
    role: Literal["admin", "manager", "operator", "reader"] | None = None
    phone: Phone | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_update_field(self) -> "UpdateOrganizationUserRequest":
        if not self.model_fields_set:
            raise ValueError("Renseignez au moins un champ à modifier.")
        return self


class OrganizationMemberResponse(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    role: Literal["owner", "admin", "manager", "operator", "reader"]
    phone: str | None
    photo_url: str | None
    is_active: bool


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: uuid.UUID
    organization_name: str
    organization_slug: str
    role: Literal["owner", "admin", "manager", "operator", "reader"]


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    phone: str | None = None
    memberships: list[MembershipResponse]
    customer_account: bool = False


class PublicAuthStatusResponse(BaseModel):
    customer_account: bool


class OrganizationUserResponse(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    role: Literal["owner", "admin", "manager", "operator", "reader"]
    phone: str | None = None
    photo_url: str | None = None
    is_active: bool = True


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    legal_form: str | None
    phone: str | None
    email: str | None
    address: str | None
    website: str | None
    facebook_url: str | None
    tiktok_url: str | None
    role: Literal["owner", "admin", "manager", "operator", "reader"]
    created_at: datetime


class UpdateOrganizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)
    ] | None = None
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=2000)
    ] | None = None
    legal_form: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=120)
    ] | None = None
    phone: Phone | None = None
    email: EmailStr | None = None
    address: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=500)
    ] | None = None
    website: HttpUrl | None = None
    facebook_url: HttpUrl | None = None
    tiktok_url: HttpUrl | None = None

    @model_validator(mode="after")
    def require_update_field(self) -> "UpdateOrganizationRequest":
        if not self.model_fields_set:
            raise ValueError("Renseignez au moins une information à modifier.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Le nom de l’entreprise ne peut pas être vide.")
        return self


class MessageResponse(BaseModel):
    message: str
