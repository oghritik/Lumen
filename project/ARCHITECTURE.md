# LUMEN Backend Architecture

This document describes the backend structure used to keep the codebase maintainable as new features are added.

## Layered Structure

- `app.py` (routing/composition layer):
  - Registers Flask routes
  - Handles request/response wiring
  - Delegates business logic to services
  - Uses shared decorators/helpers for cross-cutting concerns
- `modules/services` (business logic layer):
  - Contains route-independent workflows (dashboard payloads, receipt processing, wishlist helpers)
  - Should not depend on Flask request globals directly
- `modules/web` (web support layer):
  - Shared Flask-facing helpers (authentication decorators, session user context)
- `modules/database` (persistence layer):
  - Models and repositories
  - DB-specific data access concerns

## Current Scalability Improvements

- Centralized route auth logic in `modules/web/access.py`.
- Centralized user-email session resolution in `modules/web/user_context.py`.
- Extracted high-complexity route logic into services:
  - `modules/services/dashboard_service.py`
  - `modules/services/receipt_upload_service.py`
  - `modules/services/wishlist_service.py`

## Conventions for New Features

1. Keep route handlers thin:
   - Parse incoming request
   - Call a service function
   - Return response
2. Add reusable auth/session checks in `modules/web`.
3. Add business rules and data transformations in `modules/services`.
4. Keep SQLAlchemy queries inside repositories when possible.
5. Return stable response shapes from service functions to reduce frontend coupling.

## Recommended Workflow for Adding a Feature

1. Define route contract (request + response format).
2. Implement service function(s).
3. Reuse or add route decorators/helpers.
4. Add/extend repository methods only if persistence changes are needed.
5. Add tests around service functions first, then integration tests for routes.

## Why This Helps

- Reduces merge conflicts in `app.py`.
- Makes behavior easier to test in isolation.
- Improves onboarding for new developers by giving clear extension points.
- Lowers risk when changing one area of functionality.
