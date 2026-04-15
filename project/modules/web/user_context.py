"""User/session helpers shared across web routes."""

from flask import session
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def get_or_cache_user_email() -> str | None:
    """Return user email from session; fetch once from Gmail profile if missing."""
    user_email = session.get("user_email")
    if user_email:
        return user_email

    credentials_payload = session.get("credentials")
    if not credentials_payload:
        return None

    creds = Credentials(**credentials_payload)
    gmail = build("gmail", "v1", credentials=creds)
    profile = gmail.users().getProfile(userId="me").execute()
    user_email = profile.get("emailAddress")

    if user_email:
        session["user_email"] = user_email

    return user_email
