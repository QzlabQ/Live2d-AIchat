from __future__ import annotations

from pydantic import BaseModel


class VisitorRecommendationRequest(BaseModel):
    interest_tags: list[str]
    visitor_profile: str | None = None


class VisitorRecommendationResponse(BaseModel):
    route_title: str
    intro: str
    highlights: list[str]
    suggested_questions: list[str]
    applied_interest_tags: list[str]
