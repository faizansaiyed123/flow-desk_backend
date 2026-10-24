"""The authenticated + tenant-scoped context attached to every protected
request. Passing this single object into service functions (instead of
separate user/tenant/role args scattered everywhere) makes it structurally
obvious, at every call site, which tenant a query is scoped to."""
import uuid
from dataclasses import dataclass

from app.models.membership import MembershipRole
from app.models.user import User


@dataclass(frozen=True)
class AuthContext:
    user: User
    tenant_id: uuid.UUID
    role: MembershipRole
    membership_id: uuid.UUID
