"""User / personalization package (Gate 8)."""

from app.services.user.profile import UserProfile, UserProfileService, build_user_profile_service

__all__ = [
    "UserProfile",
    "UserProfileService",
    "build_user_profile_service",
]
