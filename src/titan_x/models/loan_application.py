from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin


class LoanApplication(PrimaryKeyMixin, Base):
    __tablename__ = "loan_applications"

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    mobile: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    pan_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stage: Mapped[str] = mapped_column(String(50), nullable=False, default="MOBILE_VERIFICATION", index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="IN_PROGRESS", index=True)
    documents_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    analyses_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    verification_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_grade: Mapped[str | None] = mapped_column(String(10), nullable=True)
    offer_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict[str, Any]:
        import json

        return {
            "id": self.id,
            "user_id": self.user_id,
            "mobile": self.mobile,
            "pan": self.pan,
            "pan_name": self.pan_name,
            "customer_name": self.customer_name,
            "stage": self.stage,
            "status": self.status,
            "documents": json.loads(self.documents_json or "{}"),
            "analyses": json.loads(self.analyses_json or "{}"),
            "verification": json.loads(self.verification_json or "{}"),
            "score": self.score,
            "risk_grade": self.risk_grade,
            "offer": json.loads(self.offer_json or "{}"),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
