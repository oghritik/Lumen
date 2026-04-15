"""Web-layer access control helpers for route authorization."""

from functools import wraps
from flask import jsonify, redirect, session, url_for


def require_auth(*, allow_guest: bool = False, api: bool = False):
    """
    Enforce session authentication for Flask routes.

    Args:
        allow_guest: Allow guest mode sessions when True.
        api: Return JSON 401 for APIs instead of redirect when True.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            has_credentials = "credentials" in session
            has_guest_access = bool(session.get("guest_access"))

            if has_credentials or (allow_guest and has_guest_access):
                return view_func(*args, **kwargs)

            if api:
                return jsonify({"success": False, "error": "Not authenticated"}), 401

            return redirect(url_for("index"))

        return wrapper

    return decorator
