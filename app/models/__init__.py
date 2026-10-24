"""Import every model so Base.metadata is fully populated for Alembic
autogenerate and for create_all() in tests."""
from app.models.tenant import Tenant  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.membership import Membership, MembershipRole, ROLE_RANK  # noqa: F401
from app.models.client import Client  # noqa: F401
from app.models.project import Project, ProjectStatus, BillingType  # noqa: F401
from app.models.task import Task, TaskComment, TaskStatus, TaskPriority  # noqa: F401
from app.models.time_entry import TimeEntry  # noqa: F401
from app.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus  # noqa: F401
from app.models.notification import Notification, NotificationType  # noqa: F401
from app.models.activity import ActivityLog  # noqa: F401
from app.models.attachment import Attachment  # noqa: F401
from app.models.api_key import ApiKey  # noqa: F401
from app.models.webhook import Webhook, WebhookDelivery, WebhookEvent  # noqa: F401
from app.models.invitation import Invitation, InvitationStatus  # noqa: F401
from app.models.password_reset import PasswordResetToken  # noqa: F401
