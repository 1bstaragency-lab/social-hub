# SoundCloud Browser Auth — Integration Guide

## What was added

### New files
- `backend/app/services/soundcloud_auth.py` — Playwright-based login + token capture
- `backend/app/api/endpoints/soundcloud_auth.py` — API endpoints (login/validate/relogin)
- `frontend/src/components/accounts/SoundCloudLoginForm.jsx` — Login form component
- `frontend/src/components/accounts/SCAccountCard.jsx` — Enhanced account card

### Removed
- `social-hub-oauth/` — Obsolete Go OAuth microservice (SC dev portal is private)

---

## Manual integration steps

### 1. Register the new API router

In `backend/app/api/router.py` (or wherever routes are aggregated), add:

```python
from app.api.endpoints.soundcloud_auth import router as sc_auth_router

api_router.include_router(sc_auth_router, prefix="/api/v1")
```

### 2. Update AddAccountModal.jsx

In `frontend/src/components/accounts/AddAccountModal.jsx`, add the import and
conditionally render the new form for SoundCloud:

```jsx
import SoundCloudLoginForm from "./SoundCloudLoginForm";

// Inside the modal body, where you render platform-specific fields:
{selectedPlatform === "soundcloud" ? (
  <SoundCloudLoginForm
    onSuccess={(data) => {
      onClose();
      if (onAccountAdded) onAccountAdded(data);
    }}
    onError={(msg) => setError(msg)}
    onClose={onClose}
  />
) : (
  // ... existing form for other platforms
)}
```

### 3. Update AccountList.jsx

In `frontend/src/components/accounts/AccountList.jsx`, use SCAccountCard for
SoundCloud accounts:

```jsx
import SCAccountCard from "./SCAccountCard";

// In the account list render:
{accounts.map((account) =>
  account.platform === "soundcloud" ? (
    <SCAccountCard key={account.id} account={account} onRefresh={fetchAccounts} />
  ) : (
    <AccountCard key={account.id} account={account} />
  )
)}
```

### 4. Update SoundCloud client.py (backend)

In `backend/app/platforms/soundcloud/client.py`, add the import:

```python
from app.services.soundcloud_auth import SoundCloudAuthService
```

Update `authenticate()` to try OAuth token first, fall back to browser session, and auto-relogin with stored email/password if session expired.

Update `health_check()` to call the new `authenticate()` and return profile data along with validity status.

### 5. Add fields to SocialAccount model

If not already present, add to `backend/app/models/social_account.py`:

```python
track_count = Column(Integer, default=0)
profile_url = Column(String, nullable=True)
is_verified = Column(Boolean, default=False)
```

Then run: `alembic revision --autogenerate -m "add SC profile fields"` and `alembic upgrade head`

### 6. Install Playwright browsers (deployment)

```bash
pip install playwright
playwright install chromium
```

For Docker, add to Dockerfile:
```dockerfile
RUN pip install playwright && playwright install --with-deps chromium
```

---

## How it works

1. User enters email + password in the SoundCloudLoginForm
2. Backend launches headless Chromium via Playwright
3. Browser automation fills the login form and submits
4. Token captured via network interception, localStorage, cookies, and page hydration
5. Profile data fetched from SC API or scraped from page state
6. Session persisted to browser_sessions/{account_id}/state.json
7. Credentials encrypted with Fernet and stored in AccountCredential table
8. Health check re-validates session; auto-relogs if expired
