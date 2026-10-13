# M3.2 — Citizen / User Authentication Documentation

## 1. Executive Summary & Scope

Module M3.2 introduces secure, persistent citizen identity and authentication to the CVKI civic platform. It ensures that civic complaints created by citizens are strictly associated with authenticated user accounts, establishing ownership integrity and multi-tenant data isolation.

### Strict Scope Boundaries
- **In Scope (M3.2):**
  - Citizen account registration (`POST /api/v1/auth/register`).
  - Citizen sign-in (`POST /api/v1/auth/login`).
  - Citizen session retrieval (`GET /api/v1/auth/me`).
  - Password hashing with `bcrypt` (salted, standard work factor).
  - Stateless JSON Web Token (JWT) generation and verification (`HS256`).
  - FastAPI reusable security dependency (`get_current_user`).
  - Case ownership binding: deriving `user_id` strictly from JWT claims on case creation.
  - Ownership protection on case retrieval (`GET /cases/{reference_id}`) and status checks (`GET /cases/{reference_id}/status`).
- **Explicitly Out of Scope (NOT implemented):**
  - Government portal submission or automated external filing.
  - External government API integration.
  - Authority contact database creation or live dialing.
  - Advanced NLP / duplicate complaint detection / priority scoring.
  - Admin dashboards, roles, or permission hierarchies.
  - Email, SMS, or OTP verification systems.
  - Social authentication (Google, Facebook, etc.).
  - Password reset flows.
  - YOLO retraining, dataset expansion, or modifying frozen CV model artifacts (`best.pt`).

---

## 2. Architecture & Design

```
Citizen Browser
   │
   ├── 1. Register / Login (email, password)
   │      │
   │      ▼
   │   FastAPI Auth Router (/api/v1/auth)
   │      │
   │      ├── Normalize email (lowercase, stripped)
   │      ├── Hash password with bcrypt (or verify hash)
   │      └── Persist to MongoDB `users` collection (unique email index)
   │
   └── 2. Receives JWT (Bearer token)
          │
          ▼
   Subsequent Protected Requests (Authorization: Bearer <token>)
          │
          ▼
   FastAPI Dependency (`get_current_user`)
          │
          ├── Decode & verify JWT signature and expiry
          ├── Extract `sub` claim as `user_id`
          ├── Verify active status in MongoDB `users`
          └── Inject authenticated `UserResponse` into route handler
```

---

## 3. User Data Model & MongoDB Schema

Collection: `users`

| Field | Type | Description | Privacy / Security |
| :--- | :--- | :--- | :--- |
| `user_id` | String | Unique UUIDv4 identifier (`usr_...` format) | Public safe identifier |
| `email` | String | Normalized lowercase email address | Unique index enforced |
| `password_hash` | String | Bcrypt hash with per-user salt | **Never exposed in any API response or log** |
| `is_active` | Boolean | Whether account is active (default: `true`) | Account state flag |
| `created_at` | DateTime | ISO 8601 UTC creation timestamp | Audit trail |
| `updated_at` | DateTime | ISO 8601 UTC last update timestamp | Audit trail |

### Minimization of Personal Identifiable Information (PII)
In adherence to privacy-by-design principles, the citizen schema does **not** collect phone numbers, street addresses, Aadhaar, PAN, voter IDs, or social handles.

### MongoDB Indexes
- Unique index on `email`: `{ "email": 1 }` (unique constraint prevents race-condition duplicates).
- Unique index on `user_id`: `{ "user_id": 1 }`.

---

## 4. Password Hashing & Security Decisions

1. **Bcrypt Password Hashing:**
   - Hashing is handled through Python's established `bcrypt` library (`gensalt()`).
   - Plaintext passwords are never stored in MongoDB or kept in memory past request validation.
   - Password strength: Minimum 8 characters enforced at schema level.
2. **Safe Credential Verification:**
   - Login attempts compare passwords via `bcrypt.checkpw(password.encode('utf-8'), hash.encode('utf-8'))`.
   - Invalid email or password returns generic `401 Unauthorized` with `"Invalid email or password."`, avoiding user-enumeration side-channel leaks.
3. **Password Hash Redaction:**
   - `UserResponse` explicitly omits `password_hash`. All API responses return safe metadata only.

---

## 5. JWT Authentication Flow

- **Algorithm:** `HS256` (HMAC with SHA-256).
- **Configuration (via environment):**
  - `JWT_SECRET`: Configured in `.env` / `config.py` (production requires high-entropy secret).
  - `JWT_ALGORITHM`: `"HS256"`.
  - `ACCESS_TOKEN_EXPIRE_MINUTES`: `30` minutes default.
- **Token Claims:**
  ```json
  {
    "sub": "usr_c34b17a02c5240ff8d80486cb4f28522",
    "email": "citizen@example.com",
    "exp": 1791705600,
    "iat": 1791703800
  }
  ```
- **Validation:**
  - Token signature, expiration (`exp`), and algorithm are verified on every protected request.
  - Expired, forged, or malformed tokens immediately return `401 Unauthorized`.

---

## 6. Protected Endpoints & Ownership Enforcement

| Endpoint | Method | Authentication Required | Ownership Requirement |
| :--- | :--- | :--- | :--- |
| `/api/v1/auth/register` | `POST` | No | Public |
| `/api/v1/auth/login` | `POST` | No | Public |
| `/api/v1/auth/me` | `GET` | **Yes** | Returns active citizen identity |
| `/api/v1/complaint/cases` | `POST` | **Yes** | Attaches `user_id = current_user.user_id` |
| `/api/v1/complaint/cases/{ref}` | `GET` | **Yes** | Returns 404 unless `case.user_id == current_user.user_id` |
| `/api/v1/complaint/cases/{ref}/status` | `GET` | **Yes** | Returns 404 unless `case.user_id == current_user.user_id` |
| `/api/v1/complaint/cases/my` | `GET` | **Yes** | Returns only cases where `case.user_id == current_user.user_id` |

### Security Isolation Rule
If Citizen A attempts to access Citizen B's complaint case or status, the server returns `404 Not Found` (`"CVKI case was not found."`). This prevents unauthorized users from inferring the existence of other citizens' complaint reference IDs.

---

## 7. Test Suite Summary

M3.2 includes 18 dedicated automated tests in `backend/tests/test_auth_api.py`:
1. Registration success with 201 Created.
2. Duplicate email rejection with 409 Conflict.
3. Invalid email format rejection.
4. Weak password rejection (< 8 chars).
5. Password is hashed with bcrypt in MongoDB.
6. Password hash is never returned in API responses.
7. Login success returning valid JWT access token.
8. Invalid credentials return safe 401 error.
9. JWT contains stable `sub = user_id` and correct expiry.
10. Expired or invalid JWT returns 401 Unauthorized.
11. Missing Authorization header returns 401 Unauthorized.
12. Protected endpoint access without token returns 401 Unauthorized.
13. Authenticated case creation persists case with citizen's `user_id`.
14. `user_id` comes strictly from JWT `sub`, never from request body.
15. User can retrieve their own case details.
16. User cannot retrieve another user's case (returns safe 404).
17. User cannot retrieve another user's case status (returns safe 404).
18. User history endpoint returns only cases belonging to the authenticated user.

---

## 8. Known Limitations

- **Academic Browser Storage:** JWT access tokens are stored in browser `localStorage` for development convenience. For production deployment, hardened `HttpOnly` Secure cookies with SameSite flags and CSRF defense should be employed.
- **Token Revocation / Blacklisting:** Tokens remain valid until expiration. Future modules could add a redis token blacklist for immediate logout invalidation.
- **Password Recovery:** Password reset and email confirmation flows are deliberately omitted from M3.2's strict scope.
