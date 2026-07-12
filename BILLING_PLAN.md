# Billing + Org Structure — implementation contract

Status: plan agreed 2026-07-11. Decisions locked by Nick:

1. **Billing attaches to Org, always.** A solo signup auto-creates a personal org. There is
   no user-held subscription.
2. **Seats + usage guardrails.** Seat count drives the Stripe quantity. The existing
   `LlmUsage` dollar budgets stay a runaway-stop, not a billing meter.
3. **Full self-service in v1**: Stripe Checkout, Stripe Customer Portal, in-app org console
   with invitations.
4. **`User.tier` survives as a derived cache**, synced from Subscription by webhook. Hot-path
   readers (`chat.py`, `apps/api/auth.py`, `mcp_server/gating.py`, `tenancy/entitlement.py`)
   are NOT rewritten.

Prices are NOT decided. All price points live in Stripe and are referenced by env-configured
price IDs. Never hardcode a dollar amount in Python or TSX.

---

## 1. Schema (app: `apps/tenancy`, one migration `0002_billing`)

### `Organization` — add
| field | type | notes |
|---|---|---|
| `is_personal` | BooleanField(default=False) | auto-created at registration |
| `stripe_customer_id` | CharField(max_length=64, null=True, unique=True) | |
| `status` | extend choices | `trial, active, past_due, suspended, canceled` |
| `created_at` / `updated_at` | DateTimeField | |

`suspended` is a staff kill-switch and MUST now be enforced (today it is dead).

### `Subscription` — becomes org-only + billing-anchored
- **DROP** the `user` FK and the `subscription_org_xor_user` CheckConstraint.
- `org` becomes non-nullable.
- `product` becomes **nullable**. `product IS NULL` == the flagship full-corpus plan.
- Add:

| field | type | notes |
|---|---|---|
| `plan` | CharField, choices mirror `User.Tier` (`free/solo/firm/custom`) | |
| `stripe_subscription_id` | CharField(64, null=True, unique=True) | |
| `stripe_price_id` | CharField(64, blank=True) | |
| `seats` | PositiveIntegerField(default=1) | Stripe quantity |
| `current_period_end` | DateTimeField(null=True) | |
| `cancel_at_period_end` | BooleanField(default=False) | |
| `trial_end` | DateTimeField(null=True) | |
| `past_due_since` | DateTimeField(null=True) | grace-window anchor |

- `status` choices: `trial, active, past_due, canceled, unpaid`.
- Unique constraint: one subscription per `(org, product)` — replaces the two conditional ones.

### `OrgMembership` — activate it
- `role` (owner/admin/member) is currently **stored but never read**. It becomes load-bearing.
- Add `created_at`. Keep `unique(user, org)`. Multi-org membership stays legal.
- Invariant: **an org always has ≥1 owner.** Enforce in service layer, not DB.

### `OrgInvitation` — new
| field | type |
|---|---|
| `org` | FK(Organization, CASCADE) |
| `email` | EmailField (lowercased) |
| `role` | same choices as membership, default `member` |
| `token_hash` | CharField(64, unique) — SHA-256 of the raw token; raw token is emailed, never stored |
| `invited_by` | FK(User, SET_NULL, null=True) |
| `expires_at` | DateTimeField (default now + 14 days) |
| `accepted_at` / `revoked_at` | DateTimeField(null=True) |

Unique partial index: one *pending* invitation per `(org, email)`.

### `LlmUsage` (`apps/api/models.py`) — add org dimension
- Add `org` FK(`tenancy.Organization`, SET_NULL, null=True, db_index=True).
- Set it at capture time from the user's billing org. Nullable for background jobs.
- This is for future org-level reporting; it does NOT change how budgets are enforced.

### Backfill (same migration, `RunPython` with a reverse that is a no-op)
For every existing `User`:
1. Create `Organization(is_personal=True, status=active, name="<full_name or email> (Personal)")`,
   slug derived from the email local-part, de-duplicated with a numeric suffix.
2. Create `OrgMembership(user, org, role=OWNER)`.
3. If `user.tier != free`: create `Subscription(org, product=None, plan=user.tier,
   status=ACTIVE, seats=1)` — a comped/manual subscription with no Stripe ID.

Then migrate the 2 pre-existing seeded rows: any `Subscription` with a `user` FK moves to that
user's new personal org, preserving `product`. Any existing non-personal `Organization`
(e.g. `iowa-bar`) is left alone with `is_personal=False`.

Migration must be **idempotent and re-runnable on a partially-migrated DB** — check for an
existing personal org before creating one.

---

## 2. Service layer (`apps/tenancy/services.py`, new)

```python
PLAN_RANK = {"free": 0, "solo": 1, "firm": 2, "custom": 3}

def billing_org(user) -> Organization       # the user's personal org (is_personal=True)
def orgs_for(user) -> QuerySet[Organization]
def effective_plan(user) -> str             # max PLAN_RANK over orgs granting a live plan
def sync_user_tier(user) -> bool            # write effective_plan onto user.tier; return changed
def sync_org_tiers(org) -> None             # sync_user_tier for every member
def seat_count(org) -> int                  # OrgMembership.objects.filter(org=org).count()
```

**`effective_plan` grant rule** — an org grants its `Subscription.plan` iff:
- `org.status not in {suspended, canceled}`, AND
- `subscription.product is None` (flagship), AND
- `subscription.status in {trial, active}`, OR
  `subscription.status == past_due` AND `past_due_since > now - PAST_DUE_GRACE_DAYS` (default 7,
  from settings).

Otherwise that org contributes `free`. A user with no live plan anywhere → `free`.

This means `canceled`, `unpaid`, `suspended`, and expired-grace `past_due` all collapse to
`free`, and every existing tier gate enforces them with **zero new enforcement code**.

**Membership mutations** (`add_member`, `remove_member`, `change_role`) live here, and each one:
1. mutates membership, 2. calls `sync_org_tiers(org)`, 3. calls
   `billing.seats.sync_seats(org)` (no-op if the org has no Stripe subscription),
4. writes an `AuditEvent`.

Refuse to remove/demote the last owner.

### `apps/tenancy/entitlement.py` — minimal edit
Keep the signature `is_entitled(user, product)`. Replace the `FULL_CORPUS_TIERS` check with
`effective_plan(user) in FULL_CORPUS_PLANS` and the org-subscription query with an org-only
query (no more `Q(user=user)`). Behaviour is otherwise identical.

### `reconcile_tiers` management command
Recompute `sync_user_tier` for every user, report drift, `--fix` to write. Cron-able.

---

## 3. Stripe (new app: `apps/billing`)

Add `stripe` to `backend/requirements.txt` (pin a current 2.x/1x release — check PyPI).

Settings (`core/settings.py`, all from env, all with safe empty defaults so dev boots without
Stripe configured):
`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`,
`STRIPE_PRICE_SOLO`, `STRIPE_PRICE_FIRM`, `STRIPE_PRICE_FIRM_SEAT`, `BILLING_PAST_DUE_GRACE_DAYS=7`.
If `STRIPE_SECRET_KEY` is empty, billing endpoints return 503 "billing not configured" rather
than exploding — dev and CI must still boot and pass tests.

### `apps/billing/models.py`
`StripeEvent(event_id unique, type, payload JSON, received_at, processed_at null)` — webhook
idempotency ledger. Skip any event whose `event_id` is already processed.

### `apps/billing/api.py` — ninja router mounted at `/api/billing`
All session-auth + CSRF except the webhook.

| endpoint | auth | behaviour |
|---|---|---|
| `GET /subscription` | session | current billing org, plan, status, seats used/purchased, `current_period_end`, `cancel_at_period_end`, `can_manage` (owner/admin) |
| `POST /checkout` | session, **owner/admin only** | body `{plan: "solo"\|"firm", seats?: int}`. Creates/reuses `org.stripe_customer_id`, returns a Checkout Session URL. `mode=subscription`, `client_reference_id=org.id`, `metadata={org_id}`, `quantity=max(seats, seat_count(org))`. `success_url`/`cancel_url` back to `/account/billing`. |
| `POST /portal` | session, owner/admin | Stripe Billing Portal session URL for `org.stripe_customer_id`. |
| `POST /webhook` | **auth=None, csrf_exempt** | verify signature w/ `STRIPE_WEBHOOK_SECRET`; 400 on bad sig. |

### Webhook handlers (`apps/billing/webhooks.py`)
Handle, idempotently, resolving the org via `metadata.org_id` then falling back to
`stripe_customer_id`:
- `checkout.session.completed` → attach `stripe_subscription_id`, set plan/status/seats.
- `customer.subscription.created|updated` → upsert plan (from price ID → plan map), `status`,
  `seats` (from `quantity`), `current_period_end`, `cancel_at_period_end`, `trial_end`.
  Set/clear `past_due_since` on entering/leaving `past_due`.
- `customer.subscription.deleted` → status=`canceled`.
- `invoice.payment_failed` → status=`past_due`, stamp `past_due_since` if unset.
- `invoice.paid` → clear `past_due_since`.

**Every handler ends with `sync_org_tiers(org)`.** That single call is what makes billing state
actually enforce.

### `apps/billing/seats.py`
`sync_seats(org)` → if the org has a live `stripe_subscription_id`, set the subscription item
quantity to `seat_count(org)` with `proration_behavior="create_prorations"`. Never let quantity
drop below 1. No-op (log only) when Stripe is unconfigured.

---

## 4. Org API (`apps/api/orgs.py`, ninja router at `/api/org`)

Session auth. `require_org_role(user, org, {OWNER, ADMIN})` helper; 403 otherwise.

| endpoint | behaviour |
|---|---|
| `GET /api/org` | current billing org: name, status, is_personal, members[{id,email,full_name,role,joined}], pending invitations[], seats used/purchased, my_role |
| `PATCH /api/org` | owner/admin: rename org |
| `POST /api/org/invitations` | owner/admin: `{email, role}` → create invite, email a link to `${APP_URL}/invite/<raw-token>`. 409 if already a member or a pending invite exists. |
| `DELETE /api/org/invitations/{id}` | owner/admin: revoke |
| `GET /api/org/invitations/{token}` | **auth=None**: preview an invite (org name, inviter, email, valid?) so the accept page can render pre-login |
| `POST /api/org/invitations/{token}/accept` | session: must be logged in as the invited email; creates membership, syncs tiers + seats, stamps `accepted_at` |
| `PATCH /api/org/members/{user_id}` | owner only: change role. Cannot demote the last owner. |
| `DELETE /api/org/members/{user_id}` | owner/admin: remove member (or self-leave). Cannot remove the last owner. Syncs tiers + seats. |

Invite email goes through the existing Postmark path used by `apps/mail`. Plain, short, one link.

Every mutation writes an `AuditEvent` (extend the event-type choices; new migration in
`accounts`).

### Registration hook (`apps/api/accounts.py`)
On register: create the personal org + owner membership in the same transaction. If the request
carries an `invite` token, also accept that invitation. Existing `/api/auth/me` gains
`org: {id, name, role, is_personal}` so the SPA can route.

---

## 5. Frontend (`chat-frontend`, Carbon)

- **`/account/billing`** — current plan card (plan, status badge, renewal date, seats
  used/purchased), `Upgrade` → `POST /api/billing/checkout` → `window.location = url`,
  `Manage billing` → `POST /api/billing/portal`. Owner/admin only; members see read-only state.
  A `past_due` org shows a loud inline banner with the grace deadline.
- **`/org`** — members table (email, name, role, joined, remove), role dropdown for owners,
  invite form (email + role), pending-invitations list with revoke. Seat counter that says
  plainly "adding a member adds a seat and changes your bill."
- **`/invite/[token]`** — public preview via the unauth endpoint; if logged out, send to
  login/register with `?invite=<token>`; if logged in as the right email, Accept button.
- **`shell.tsx`** — add `Organization` + `Billing` nav entries (billing under the existing
  account area). Nav gating is display-only; the server re-enforces.
- **`marketing-frontend/app/pricing/page.tsx`** — point the Solo/Firm CTAs at
  `${APP_URL}/account/billing?plan=solo|firm`. Do **not** change the displayed prices; Nick
  has not set them.

---

## 6. Tests (pytest, alongside `backend/apps/api/tests/`)

- `effective_plan` truth table: each subscription status × org status × grace window × multi-org
  max. This is the core of the whole design — test it hardest.
- Backfill migration: users at each tier → correct personal org + subscription.
- Webhook idempotency: replaying the same `event_id` twice is a no-op.
- Webhook → tier propagation: `subscription.updated(status=canceled)` drops every member to
  `free`, and a `free` user is then rejected by the existing chat/REST/MCP gates.
- Seat sync: add/remove member changes quantity; last owner cannot be removed.
- Org API authz: a `member` cannot invite, checkout, or open the portal.
- Stripe is **mocked** in all tests — no network.

---

## 6a. FROZEN response shapes (the SPA is already built against these)

The frontend shipped first and coded against these exact keys. Backend agents MUST match them
verbatim — this is no longer negotiable prose, it is a contract with shipped code.

```jsonc
// GET /api/billing/subscription
{
  "org": {"id": 1, "name": "Acme Law", "is_personal": false, "status": "active"},
  "plan": "firm",                    // free|solo|firm|custom
  "status": "active",                // trial|active|past_due|canceled|unpaid|none
  "seats_used": 4,
  "seats_purchased": 5,
  "current_period_end": "2026-08-11T00:00:00Z",   // nullable
  "cancel_at_period_end": false,
  "trial_end": null,
  "past_due_since": null,            // REQUIRED: the SPA renders the grace deadline from this
  "grace_ends_at": null,             // REQUIRED: past_due_since + BILLING_PAST_DUE_GRACE_DAYS
  "can_manage": true                 // caller is owner|admin of the org
}
// "status": "none" is legal for an org with no subscription row.

// POST /api/billing/checkout  {plan, seats?}  ->  {"url": "https://checkout.stripe.com/..."}
// POST /api/billing/portal                    ->  {"url": "https://billing.stripe.com/..."}

// GET /api/org
{
  "id": 1, "name": "Acme Law", "is_personal": false, "status": "active",
  "my_role": "owner",                                  // owner|admin|member
  "seats_used": 4, "seats_purchased": 5,
  "members": [
    {"id": 7,                                          // NOTE: this is the USER id,
                                                       // i.e. the {user_id} path param below
     "email": "a@b.com", "full_name": "A B",
     "role": "member", "joined": "2026-07-11T00:00:00Z"}
  ],
  "invitations": [
    {"id": 3, "email": "c@d.com", "role": "member",
     "invited_by": "nick@nick.law", "expires_at": "2026-07-25T00:00:00Z"}
  ]
}

// GET /api/org/invitations/{token}   (auth=None)
{"org_name": "Acme Law", "email": "c@d.com", "role": "member",
 "inviter": "nick@nick.law", "valid": true, "expires_at": "2026-07-25T00:00:00Z"}
```

Also frozen by the shipped SPA:
- `PATCH /api/org` accepts `{"name": "..."}` (owner/admin) — an invitee sees the org name in the
  invite email, so a firm must not be stuck with "Nick (Personal)".
- The register payload field carrying an invitation is named **`invite`**.
- `DELETE /api/org/members/{user_id}` must also permit **self-leave** by a plain member
  (in a non-personal org), not just owner/admin removal of others.
- Members endpoints are keyed by **user id**, not membership id.

## 7. Blocking on Nick (does not block coding)

1. Create the Stripe account + Products/Prices (test mode first); put the 3 price IDs and the
   secret/webhook keys in `backend/.env`.
2. Decide the actual price points. Marketing currently says Solo $29; LexIowa is $49/$200+$50/seat.
3. Prod migration debt must clear before deploy: `tenancy 0001`, `accounts 0005/0006`, `api 0005`,
   `mcp_server 0001` — verify what is actually applied in prod first.
