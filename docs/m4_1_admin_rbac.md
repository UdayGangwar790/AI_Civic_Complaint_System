# M4.1 — Admin RBAC & Authorization Architectural Specification

## Executive Summary

Module M4.1 establishes a secure, defense-in-depth Role-Based Access Control (RBAC) foundation for the CVKI (Civic Vision & Knowledge Intelligence) platform. It introduces canonical operational roles (`citizen`, `admin`, `authority`), reusable authorization dependencies, strict token claim validations, database-backed lazy defaulting for backward compatibility, and frontend route protection foundation.

> **Scope Freeze Declaration**: M4.1 delivers the authentication and authorization foundation only. M4.2 (Admin Dashboard), M4.3 (Case Management), M4.4 (Assignment), M4.5 (Status Workflow), M4.6 (Map Operations), M4.7 (Analytics), and M4.8 (Audit Dashboard) remain strictly deferred.

---

## 1. RBAC Architecture

The authorization model follows a layered defense-in-depth architecture:

```
[ Frontend Request ]
        │
        ├── 1. UI Route / Visibility Layer (Informational Only)
        │      • Route guards prevent unauthorized UI exposure
        │      • Unauthenticated -> Sign-in prompt
        │      • Unauthorized role -> Access Denied view
        │
        ▼
[ Backend Transport ]
        │
        ├── 2. JWT Signature & Expiration Verification
        │      • Validated with HS256 and server-side JWT_SECRET
        │      • Decodes sub (user_id), email, and signed role claim
        │
        ├── 3. Canonical Database Record Retrieval
        │      • Checks MongoDB users collection for user existence
        │      • Checks account status (is_active: True)
        │      • Derives canonical role with lazy defaulting to 'citizen'
        │
        ├── 4. Reusable Authorization Dependency (require_role / require_roles)
        │      • 401 Unauthorized if missing/corrupt credentials
        │      • 403 Forbidden if user role is not authorized
        │
        ▼
[ Protected Operational Handler ]
```

Neither frontend query strings, request headers, cookies, nor request bodies can alter or elevate authorization decisions. The backend database and verified JWT are the sole authoritative sources of truth.

---

## 2. Roles & Definitions

The system strictly enforces three distinct roles:

| Role | Operational Scope | Allowed Capabilities | Prohibited Capabilities |
| :--- | :--- | :--- | :--- |
| `citizen` | Public / Civic Reporter | • Report civic issues with CV/NLP<br>• View & track own cases<br>• View & mark own notifications<br>• Generate government submission packets for own cases | • Cannot access `/api/v1/admin/*`<br>• Cannot access `/api/v1/authority/*`<br>• Cannot access other users' cases or notifications<br>• Cannot assign cases or modify system workflows |
| `admin` | Administrative Operations | • Authenticate into administrative domain<br>• Access protected `/api/v1/admin/*` endpoints<br>• Future foundation for M4.2 dashboard, assignment, analytics | • Cannot access `/api/v1/authority/*`<br>• Cannot self-register publicly |
| `authority` | Field / Municipal Operations | • Authenticate into authority domain<br>• Access protected `/api/v1/authority/access-check`<br>• Future foundation for case review & resolution workflows | • Cannot access `/api/v1/admin/*`<br>• Cannot self-register publicly |

---

## 3. Permission Boundaries & Explicit Policy

### Administrative vs. Authority Separation Policy

CVKI implements an **explicit separate operational roles policy**:
* `admin` and `authority` are distinct operational functions.
* `admin` role grants access to `/api/v1/admin/access-check` (200), but returns **403 Forbidden** on `/api/v1/authority/access-check`.
* `authority` role grants access to `/api/v1/authority/access-check` (200), but returns **403 Forbidden** on `/api/v1/admin/access-check`.
* `citizen` role returns **403 Forbidden** on both endpoints.
* Unauthenticated requests return **401 Unauthorized**.

---

## 4. JWT Strategy & Session Representation

1. **Server-Side Token Generation**:
   `create_access_token(user_id, email, expires_delta=None, role="citizen")` encodes the user identity and signed `role` claim inside the JWT payload:
   ```json
   {
     "sub": "usr_xxxxxxxxxxxx",
     "email": "user@example.com",
     "role": "citizen",
     "iat": 1740000000,
     "exp": 1740086400
   }
   ```
2. **Backwards Compatibility**:
   The function defaults `role="citizen"`, preserving full signature compatibility with legacy M3 test suites.
3. **Database-Backed Identity Verification**:
   The `get_current_user` dependency decodes the token, extracts the subject `user_id`, and queries the MongoDB `users` collection to confirm that the account is valid, active, and retrieves the database's canonical role.
4. **Token Tampering Mitigation**:
   Any modification to the JWT `role` or `sub` in transit invalidates the cryptographic signature, immediately returning `401 Unauthorized`.

---

## 5. Authorization Dependencies

Located in [backend/app/api/deps.py](../backend/app/api/deps.py):

* `get_current_user(credentials)`:
  Extracts and verifies the JWT, checks MongoDB user status, and yields an `AuthenticatedUser` model containing `user_id`, `email`, `role`, and `is_active`.
* `require_authenticated_user`:
  Alias for `get_current_user` to declare explicit authentication requirements.
* `require_role(role: Union[str, UserRole])`:
  Factory returning a dependency enforcing that `current_user.role == role`. Returns 403 Forbidden on mismatch.
* `require_roles(*allowed_roles: Union[str, UserRole])`:
  Factory supporting multi-role checks (e.g. `require_roles("admin", "authority")`).

---

## 6. MongoDB User Schema & Migration Strategy

### Schema Update
The canonical MongoDB `users` collection documents now persist:
```json
{
  "_id": ObjectId("..."),
  "user_id": "usr_a1b2c3d4e5f6",
  "email": "citizen@example.com",
  "password_hash": "$2b$12$...",
  "role": "citizen",
  "created_at": ISODate("2026-10-13T..."),
  "updated_at": ISODate("2026-10-13T..."),
  "is_active": true
}
```

### Zero-Downtime Lazy Defaulting
* Existing users in the database created prior to M4.1 that lack the `"role"` field automatically receive `"citizen"` at query time in `MongoUserRepository.get_by_email` and `MongoUserRepository.get_by_id`.
* No destructive schema rewrite or offline migration lock is required.
* All existing citizen accounts continue functioning with zero disruption.

---

## 7. Admin / Authority Account Creation Strategy

### Prevention of Public Elevation
* The public registration endpoint (`POST /api/v1/auth/register`) strictly sets `role = "citizen"` regardless of any `role` value passed in the JSON request body.
* A citizen can never elevate themselves to `admin` or `authority` via public APIs.

### Controlled Provisioning
Administrative and authority accounts can only be provisioned via:
1. **Development Seed Script**:
   [backend/app/scripts/seed_rbac.py](../backend/app/scripts/seed_rbac.py):
   ```powershell
   python -m app.scripts.seed_rbac --bootstrap
   ```
   Or for explicit accounts:
   ```powershell
   python -m app.scripts.seed_rbac --email admin@cvki.gov.in --password YOUR_STRONG_PASSWORD --role admin
   ```
2. **Environment Variable Overrides**:
   - `CVKI_BOOTSTRAP_ADMIN_EMAIL` / `CVKI_BOOTSTRAP_ADMIN_PASSWORD`
   - `CVKI_BOOTSTRAP_AUTHORITY_EMAIL` / `CVKI_BOOTSTRAP_AUTHORITY_PASSWORD`
3. **Internal Service Helper**:
   `create_privileged_user(email, password, role)` in [backend/app/services/user.py](../backend/app/services/user.py).

---

## 8. Protected Endpoints

| Endpoint | Method | Required Role | Unauthenticated | Unauthorized Role | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/api/v1/admin/access-check` | GET | `admin` | 401 | 403 | RBAC test probe for admin gateway |
| `/api/v1/authority/access-check` | GET | `authority` | 401 | 403 | RBAC test probe for authority gateway |
| `/api/v1/auth/me` | GET | Any authenticated | 401 | — | Returns current user profile including canonical role |
| `/api/v1/complaint/cases/my` | GET | `citizen` | 401 | — | Returns authenticated citizen's cases (user-isolated) |
| `/api/v1/complaint/cases/{ref}` | GET | Owner | 401 | 404/403 | Strict citizen ownership isolation |
| `/api/v1/notifications/{id}/read` | POST | Owner | 401 | 403 | Strict notification ownership isolation |

---

## 9. Frontend Route Protection

1. **Auth State Extension**:
   `currentUser` in [frontend/src/App.jsx](../frontend/src/App.jsx) stores `role` (`currentUser.role || 'citizen'`).
2. **`RoleProtectedRoute` Component**:
   - Intercepts unauthorized navigation.
   - If not signed in: renders clean sign-in prompt with direct "Sign In" trigger.
   - If signed in with insufficient role: displays dedicated "Access Denied" view stating current user's role and required role.
3. **Placeholder Portals**:
   - `/admin` renders `AdminPlaceholderView` (accessible exclusively to `admin`).
   - `/authority` renders `AuthorityPlaceholderView` (accessible exclusively to `authority`).
   - No M4.2 dashboard, analytics, or assignment widgets are included.

---

## 10. Security Verification & Results

* **Bcrypt Password Security**: Passwords remain exclusively bcrypt-hashed. Password hashes and secrets are never returned in responses or logged.
* **Model Integrity**: YOLOv8 weights at `ai/computer_vision/training/runs/yolov8n_m1_13/weights/best.pt` verified with SHA-256 `602160D4851E0D79C34CB23B828BDE474FC4C164EAF1A1C2A884CFB372F4BDA3`.
* **Test Suite**:
  - M4.1 RBAC tests: **23 passed**
  - M1–M3.10 baseline regression: **199 passed**
  - Total test suite: **222 passed, 0 failures**
* **Frontend Verification**:
  - `oxlint`: 0 errors, 0 warnings
  - `vite build`: Succeeded in 1.13s

---

## 11. Known Limitations & Deferred Modules

* **M4.2 Admin Dashboard**: Dashboard views, operational charts, and queue metrics are NOT implemented in M4.1.
* **M4.3 Case Management & Global Search**: Admin-wide cross-citizen case browsing is scheduled for M4.3.
* **M4.4–M4.8**: Case assignment, status updates, map operations, and audit logging are strictly deferred.
