# Email Assistant Plan

**Goal:** Attorneys email an assistant address and get a cited, verified answer back by email.
Each address is a *product front door* — the email analog of `Product.hostname`:

- `assistant@mail.nick.law` → flagship (full corpus)
- `ethics@<isba-delegated-subdomain>` → `iowa-ethics-procedure` product (scope-locked to `iowa-court-rules`)
- Future products = one row in a routing table + DNS, no new code.

Status: **BUILT on dev, uncommitted** (2026-07-09). Phase 1 + the Phase-2 threading/STOP items
are implemented in `backend/apps/mail/` and verified end-to-end on dev (simulated webhook →
worker → real OpenAI turn → console reply, including a threaded follow-up). Remaining to go
live: Postmark account + DNS (Phase 0), set the two secrets in the DO UI, sync the live spec
with the new worker + envs (from the LIVE spec, per the app.yaml warning), seed the prod
address, wire `Product.system_prompt_key` (still unconsumed), bounce/complaint webhook.

---

## 1. Why this is cheap to build here

Findings from the codebase survey (2026-07-09):

1. **The chat loop is already headless.** `run_chat_turn()` (`apps/api/chat.py:1013`) is a pure
   sync function — messages in, `(answer, model)` out — with the verification gate
   (`_apply_verification` → `apps/corpus/services/answer.py:verify_answer`) inside it.
   `probe_chat` (`apps/api/management/commands/probe_chat.py:275`) already calls it with no HTTP.
   Its docstring says auth/quota/trace are the caller's job — the email worker is just another caller.
2. **Tenancy already models per-address assistants.** `Product` has `allowed_source_slugs`
   (scope lock), `system_prompt_key`, `jurisdiction`, branding, `support_email`
   (`apps/tenancy/models.py:43`). `is_entitled(user, product)` (`apps/tenancy/entitlement.py:31`)
   is a pure function reusable outside HTTP. The ISBA-style product (`iowa-ethics-procedure`) is
   already seeded by `seed_ethics_procedure_demo`.
3. **Users are keyed by email.** `USERNAME_FIELD = "email"`, unique (`apps/accounts/models.py:27,40`)
   — the From address maps straight to a `User`.
4. **A worker pattern exists.** DO App Platform has no cron, so background work runs as a
   self-looping management command worker (`purge_chat_traces --forever`, `.do/app.yaml:287`).
   The email processor is a second worker of the same shape. No broker/queue exists; DB-as-queue.
5. **Quota machinery exists.** `_enforce_chat_quota(user)` (`apps/api/chat.py:843`) takes only a
   user — directly reusable to keep the shared `OPENAI_API_KEY` bill bounded.
6. **Ingress:** `/api` already routes to the `statutes` service (`.do/app.yaml:120-164`), so the
   inbound webhook lives under `/api/email/…` with **no app.yaml ingress change**.

Gaps to design around:

- **No conversation state.** Chat is stateless (client resends full history). Email replies need
  a server-side thread model (§3).
- **`Product.system_prompt_key` is stored but never consumed.** Chat builds one global
  `SYSTEM_PROMPT` + scope preamble. This project wires it up (benefits web chat too).
- **`_enforce_product_scope` is request-shaped.** The clamp logic (~10 lines: force
  `source_slug` into `allowed_source_slugs`, drop out-of-scope `node_id`) gets extracted into a
  pure helper both the view and the email worker call.

---

## 2. ESP decision: Postmark (inbound + outbound), via django-anymail

**Recommendation: Postmark** for both directions, one account, two message streams
(inbound + transactional outbound).

| | Postmark | AWS SES | Mailgun | Resend |
|---|---|---|---|---|
| Transactional deliverability reputation | Best in class | Good (shared IPs vary) | Middling (spammy shared pools) | Good, younger |
| Inbound parsing | Built-in: full MIME → JSON webhook, incl. SPF/DKIM results and spam score | DIY: SES receive → S3 → SNS/Lambda, region-limited | Built-in routes | Newer, less proven |
| Ops burden | Minimal | Highest | Low | Low |
| Cost at our volume | $15/mo (10k msgs, inbound counts) | ~$1/mo + plumbing time | $15-35/mo | $20/mo |

Rationale: we are low-volume, deliverability-critical, and solo-operated. Postmark's inbound
webhook hands us a parsed JSON payload **with SPF/DKIM verdicts included** (we need those for
sender auth, §5), and its transactional-only sending pools are the strongest inbox-placement
story without managing IP warmup. SES is the fallback if cost ever matters; the code should not
care — use **django-anymail** (`anymail[postmark]`) as the abstraction so the backend is a
settings swap.

New env/secrets (follow the `.do/app.yaml` `type: SECRET` + set-in-UI rule — never
`doctl apps update --spec` from the repo file):

- `POSTMARK_SERVER_TOKEN` (outbound, via anymail)
- `EMAIL_INBOUND_WEBHOOK_TOKEN` (shared secret in the webhook URL/basic-auth, `hmac.compare_digest`
  like the docling token pattern)
- `DEFAULT_FROM_EMAIL` per address comes from the routing table, not settings.

---

## 3. Architecture

```
attorney ──▶ ethics@ask.isba.org
                  │  (MX → Postmark inbound)
                  ▼
        Postmark parses MIME, runs SPF/DKIM/spam checks
                  │  POST JSON webhook
                  ▼
   /api/email/inbound  (django-ninja, statutes service)
     - verify shared-secret token
     - dedupe on MessageID
     - store InboundEmail(status=pending) + match/create EmailThread
     - return 200 immediately (no LLM work in-request)
                  │
                  ▼  (DB-as-queue poll, ~5s interval)
   email-assistant worker  (manage.py process_assistant_email --forever)
     - resolve AssistantAddress → Product
     - resolve sender → User (From, only if SPF or DKIM passed)
     - gates: allowlist (pilot) → is_entitled(user, product) → _enforce_chat_quota(user)
     - loop guards: Auto-Submitted/Precedence headers, per-thread hourly cap
     - build messages[] from EmailThread history + stripped new body
     - run_chat_turn(messages, source_slug=<clamped>, model, api_key, trace)
       └─ verification gate runs inside, as in web chat
     - render reply (text + minimal HTML, citations → product URL, disclaimer footer)
     - send via anymail/Postmark; store OutboundEmail with Message-ID
                  │
                  ▼
        reply lands in the attorney's inbox, threaded
```

### New Django app: `apps/mail`

Models (avoid clashing with `django.core.mail.EmailMessage`):

- **`AssistantAddress`** — the routing table. `address` (unique, lowercased), FK `product`
  (nullable = flagship/full corpus), `active`, `mode` (`allowlist` | `entitled` | `open_reject`),
  `model` (default `gpt-5-mini`), `display_name` ("Hudson Research Assistant"),
  `signature`/`disclaimer` overrides, `max_daily_per_sender`.
- **`AddressAllowlist`** — pilot gating: FK address, `email`, `note`.
- **`EmailThread`** — conversation state the stateless chat loop needs. FK `address`, FK `user`,
  `subject`, `token` (short id used in plus-addressing, e.g. `assistant+t_ab12cd@…` as Reply-To),
  `messages` JSONField (the exact `[{role, content}]` history to replay into `run_chat_turn`),
  `turn_count`, `last_activity`, `status` (open/closed/suppressed).
- **`InboundEmail`** — raw audit + queue row. `message_id` (unique — dedupe key; Postmark retries
  on non-200), `in_reply_to`, `references`, `from_email`, `to_email`, `spf_pass`, `dkim_pass`,
  `spam_score`, `stripped_text`, `raw_payload` JSON, FK `thread` (nullable until matched),
  `status` (pending/processing/answered/rejected/failed/ignored), `reject_reason`, `attempts`.
- **`OutboundEmail`** — `message_id` (ours, for threading), FK `thread`, FK `in_reply_to_inbound`,
  `body_text`, `provider_message_id`, `status` (sent/bounced/complained), timestamps.

### Inbound webhook (`apps/api/` or `apps/mail/api.py`, mounted under `/api/email/inbound`)

- Auth: constant-time compare of a token segment in the URL (Postmark supports basic-auth URLs);
  optionally also restrict by Postmark's published webhook IPs.
- Idempotent: `get_or_create` on `message_id`; return 200 on duplicates.
- Does **no** LLM work (chat turns run 30–120s; Postmark times out ~30s and retries → duplicate
  answers). Store-and-ack only.

### Worker (`process_assistant_email --forever`)

Copy the `purge_chat_traces` shape exactly (internal loop, per-pass try/except, single argv, no
bash in the image). Add a `workers:` entry in `.do/app.yaml` reusing the Django image.
Poll `InboundEmail(status=pending)` with `select_for_update(skip_locked=True)` so a second worker
instance is safe later. Retry failed turns up to N times with backoff; then send an apologetic
"couldn't complete this one" reply and mark failed.

### Threading

1. Primary: `In-Reply-To`/`References` matched against stored `OutboundEmail.message_id`.
2. Fallback: plus-address token — our replies set `Reply-To: assistant+<thread.token>@…`, and the
   inbound handler parses the token from the To address. Survives clients that mangle headers.
3. Else: new thread. Cap replayed history (last ~10 turns) to bound tokens.
4. Body hygiene: strip quoted reply chains and signatures before appending to history
   (`email-reply-parser` dependency, or Postmark's `StrippedTextReply` field which does this for us
   — prefer Postmark's, fall back to full text body).

### Prompt/product wiring

- Resolve scope: `source_slug = product.allowed_source_slugs[0]` when scoped (same clamp as
  `_enforce_product_scope`); flagship = unscoped.
- **Wire `Product.system_prompt_key`**: registry `SYSTEM_PROMPTS = {"default": …, "ethics-procedure": …}`
  consulted by prompt assembly in `chat.py` — shared with the web app, closing the known gap.
- Add a small email-context preamble ("You are answering by email; be complete in one reply,
  cite precisely; the reader may not reply promptly") keyed off the caller, not a fork of the loop.

### Reply rendering

- `text/plain` primary + minimal HTML alternative (no images, no tracking pixels, few links).
- Citations rendered as links to the product's host (`corpus.nick.law/...` or the product
  hostname) — link count kept low for spam-filter hygiene.
- Footer, non-negotiable: "AI-generated research assistance for licensed attorneys — not legal
  advice. Citations verified against the Iowa corpus as of <date>. Reference: <thread.token>."
  Plus the product `disclaimer` field if set, and an opt-out line ("Reply STOP to stop").
- Subject: `Re: <original subject>`; headers `In-Reply-To` + `References` set from the inbound.

---

## 4. Deliverability plan (staying out of spam)

The structural advantage: **we send 1:1 replies to people who emailed us first.** That is the
lowest-spam-risk sending pattern that exists — recipient-initiated, low volume, transactional.
The plan is to not squander it:

1. **Dedicated subdomain per brand, never the apex.**
   - Hudson: `mail.nick.law` (sending + inbound MX). Root `nick.law` reputation stays insulated.
   - ISBA: never send as `@isba.org` without delegation. The runbook is: ISBA creates a
     subdomain (e.g. `ask.isba.org`), adds our Postmark DKIM CNAMEs + return-path CNAME + MX
     records to it. Then `ethics@ask.isba.org` sends DKIM-aligned as their brand, and their apex
     is never touched. This is the standard ESP delegation pattern; it's ~4 DNS records on their
     side and it's what makes the "sell the address to ISBA" model legitimate.
2. **Authentication trifecta on every sending subdomain:** SPF (via return-path CNAME), DKIM
   (Postmark CNAMEs), and DMARC — start `p=none` with `rua=` reports for two weeks, then move to
   `p=quarantine`. Alignment matters more than policy strictness for inboxing.
3. **Transactional stream only.** Assistant replies go on Postmark's transactional stream. If we
   ever send digests/newsletters (`weekly_digest` flag exists in UserProfile), those go on a
   separate broadcast stream — never mixed, so a marketing complaint can't hurt assistant replies.
4. **Content hygiene:** mostly-text, consistent From name+address, no link shorteners, no
   attachments, open/click tracking OFF (tracking rewrites links through ESP domains and hurts
   both trust and filters).
5. **Bounce/complaint webhooks** (Postmark → `/api/email/events`): hard bounce or complaint →
   suppress the address (`EmailThread.status=suppressed`), never auto-send to it again. This is
   the metric ESPs and receivers score us on.
6. **No warmup needed** at pilot volume (<100/day), but ramp naturally — the allowlist pilot does
   this for free.
7. **Never SMTP from droplets/App Platform IPs.** Cloud-provider IP ranges have poor baseline
   reputation and DO blocks/discourages port 25; this is precisely what the ESP is for.
8. **Loop protection** (protects reputation *and* the OpenAI bill): never reply to
   `Auto-Submitted: auto-*`, `Precedence: bulk/junk/list`, or `X-Autoreply` messages; per-sender
   daily cap (`AssistantAddress.max_daily_per_sender`, default ~10); per-thread hourly cap (2);
   never reply to bounces/DSNs (null return-path).

---

## 5. Security & trust gates (order of checks in the worker)

1. **Webhook authenticity:** shared-secret URL token, constant-time compare.
2. **Sender authenticity:** require Postmark's SPF **or** DKIM pass on the inbound; fail → status
   `ignored` (no reply — replying to a spoofed From is a backscatter vector).
3. **Identity:** `From` → `User` lookup (email is the username field). Unknown sender behavior is
   per-address `mode`: pilot = allowlist-only (silent ignore), later = one polite "this assistant
   is for <product> subscribers — sign up at <url>" reply, at most once per address per month.
4. **Entitlement:** `is_entitled(user, product)` for scoped addresses — reuses the exact web
   logic (individual sub ∪ org sub ∪ full-corpus tier).
5. **Quota:** `_enforce_chat_quota(user)` (daily per-user + global monthly), plus the per-sender
   address cap. Email answers use the *deep* pipeline, so they're the expensive turns.
6. **Reply only to the authenticated address on file** — never to a different Reply-To than the
   verified sender without a match.
7. **Prompt injection surface:** email body is untrusted input, but the loop's tools are
   read-only corpus tools and `source_slug` is re-forced on every tool call inside the loop
   (`chat.py:1151`), so the blast radius is "weird answer," not data access. v1 ignores
   attachments entirely (reply notes that).
8. **Confidentiality:** attorneys will email client facts. (a) ToS/first-reply footer states how
   content is stored; (b) buy Postmark's Retention Add-on and set retention to the 7-day minimum
   (default is 45; content is fully purged after the window, verified from their docs 2026-07);
   (c) sign their GDPR DPA; (d) inbound bodies live in our PG under the same posture as
   ChatTrace; decide a retention window (reuse the trace-purge worker pattern) — propose 90 days
   for `raw_payload`, keep `messages` history for open threads only.

   **Postmark vendor-risk facts (verified 2026-07):** TLS on SMTP/API/HTTPS; cold data at rest
   encrypted, but live message content is NOT encrypted-at-rest in a way that prevents
   operational access, and staff may view content during compliance reviews. **Postmark itself
   has no product-level SOC 2 audit — only its data centers (Deft, AWS) do.** No HIPAA BAA
   historically (do not route PHI; say so in ToS). If an org customer's vendor review requires
   an audited ESP, the exit path is AWS SES (in AWS's SOC 2/HIPAA scope): anymail makes outbound
   a settings swap; inbound would need SES→S3→SNS plumbing (~2-3 days rework).

---

## 6. Build phases

### Phase 0 — Accounts & DNS (half a day, mostly waiting on DNS)
Postmark account + server; verify `mail.nick.law` (DKIM/return-path CNAMEs); MX for inbound on
`mail.nick.law`; DMARC `p=none` + reports; app.yaml secrets added in DO UI.

### Phase 1 — Flagship MVP behind an allowlist (~3–5 days of work)
- `apps/mail` app: models + migrations, admin registrations.
- `anymail[postmark]` + `email-reply-parser` deps; `EMAIL_BACKEND` settings.
- Inbound webhook endpoint + token auth + dedupe.
- `process_assistant_email --forever` worker + `.do/app.yaml` worker entry.
- Extract scope-clamp helper from `_enforce_product_scope`; call `run_chat_turn` headlessly with
  trace capture (`record_chat_trace`) so email turns land in ChatTrace like web turns.
- Reply renderer + threading headers + disclaimer footer.
- Loop guards + allowlist mode.
- Seed `assistant@mail.nick.law` → flagship; allowlist Nick + 5–10 friendly attorneys.
- **Exit criteria:** email in → verified, cited answer back in <5 min; duplicate webhook
  deliveries produce one reply; auto-responder in → no reply out.

### Phase 2 — Threads + multi-assistant (~2–3 days)
- Reply threading (headers + plus-address fallback), history replay with turn cap.
- Wire `Product.system_prompt_key` into prompt assembly (web + email).
- `mode=entitled` for scoped addresses; seed `ethics@mail.nick.law` → `iowa-ethics-procedure`
  as the internal demo of the ISBA shape.
- Bounce/complaint webhook + suppression.

### Phase 3 — Hardening & ISBA readiness
- Retry/backoff + failure-notice emails; ops metrics (pending age, failure rate) on the
  admin/health surface; inbound retention purge.
- DMARC to `p=quarantine`.
- ISBA delegation runbook doc (the 4 DNS records + address seeding) — the sellable artifact.
- Optional: "STOP" handling, digest of unanswered/failed items to support_email.

## 7. Open decisions (need Nick)

1. **Address naming** — `assistant@mail.nick.law` vs something friendlier (`ask@`, `research@`).
   Cheap to change pre-pilot, annoying after.
2. **Unknown-sender behavior post-pilot** — silent ignore vs one-time signup pointer (lead-gen
   vs backscatter risk; recommend the one-time pointer with the monthly cap).
3. **Pilot roster** — which 5–10 attorneys.
4. **Model for email turns** — email tolerates latency; consider defaulting email to a stronger
   model than web chat (`gpt-5` vs `gpt-5-mini`) since turns/day are quota-capped anyway.
5. **Retention window** for inbound raw content (proposed 90 days).
