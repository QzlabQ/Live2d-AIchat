from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class VisitorRecommendationRequest(BaseModel):
    interest_tags: list[str] = Field(min_length=1)
    visitor_profile: str | None = None

    @field_validator("interest_tags", mode="before")
    @classmethod
    def validate_interest_tags(cls, value: object) -> object:
        if not isinstance(value, list):
            return value

        normalized = [" ".join(str(item).strip().split()) for item in value]
        if not normalized or any(not item for item in normalized):
            raise ValueError("interest_tags must contain at least one non-empty tag.")
        return normalized


class VisitorRecommendationResponse(BaseModel):
    route_title: str
    intro: str
    highlights: list[str]
    suggested_questions: list[str]
    applied_interest_tags: list[str]
