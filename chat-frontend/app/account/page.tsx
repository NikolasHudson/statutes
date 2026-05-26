"use client";

// Account settings page. Mirrors the legacy MUI AccountPage:
//   - Profile (name + email)
//   - Password change
//   - API keys (list, create with one-time raw-key reveal, revoke)
//   - MCP config snippet for Claude Desktop / Cursor / etc.
// Sidebar shows the same Hudson Legal Tech brand + a section anchor list,
// with the shared theme/user footer used across /chat and /browse.

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircleIcon,
  CheckIcon,
  CopyIcon,
  KeyIcon,
  Loader2Icon,
  PlusIcon,
  SettingsIcon,
  TrashIcon,
  UserIcon,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AppSidebarFooter } from "@/components/app-sidebar-footer";
import { AppSidebarNav } from "@/components/app-sidebar-nav";
import { useAuth, type AuthUser } from "@/components/auth-gate";
import {
  AccountError,
  changePassword,
  createKey,
  fetchPublicConfig,
  fmtDate,
  fmtDateTime,
  listKeys,
  revokeKey,
  updateProfile,
  type APIKey,
  type CreatedAPIKey,
} from "@/lib/iowa-account";

const SECTIONS = [
  { id: "profile", label: "Profile", icon: UserIcon },
  { id: "password", label: "Password", icon: KeyIcon },
  { id: "api-keys", label: "API keys", icon: SettingsIcon },
  { id: "mcp", label: "MCP config", icon: SettingsIcon },
] as const;

export default function AccountPage() {
  return (
    <SidebarProvider>
      <div className="flex h-dvh w-full pr-0.5">
        <AccountSidebar />
        <SidebarInset>
          <header className="flex h-16 shrink-0 items-center gap-3 border-b px-4">
            <SidebarTrigger />
            <Separator orientation="vertical" className="mr-2 h-4" />
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbPage>Account</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </header>

          <main className="flex-1 overflow-y-auto px-6 py-8 md:px-10 lg:px-16">
            <div className="mx-auto flex max-w-3xl flex-col gap-12">
              <ProfileSection />
              <PasswordSection />
              <ApiKeysSection />
              <McpConfigSection />
            </div>
          </main>
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

function AccountSidebar() {
  return (
    <Sidebar>
      <SidebarHeader className="mb-2 border-b">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link href="/">
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                  <UserIcon className="size-4" />
                </div>
                <div className="me-6 flex flex-col gap-0.5 leading-none">
                  <span className="font-semibold">Hudson Legal Tech</span>
                  <span className="text-sidebar-foreground/60 text-xs">
                    Account settings
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent className="px-2">
        <AppSidebarNav />
        <SidebarGroup>
          <SidebarGroupLabel>On this page</SidebarGroupLabel>
          <SidebarMenu>
            {SECTIONS.map((s) => {
              const Icon = s.icon;
              return (
                <SidebarMenuItem key={s.id}>
                  <SidebarMenuButton asChild>
                    <a href={`#${s.id}`}>
                      <Icon className="size-4" />
                      <span>{s.label}</span>
                    </a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarRail />

      <SidebarFooter className="border-t">
        <AppSidebarFooter />
      </SidebarFooter>
    </Sidebar>
  );
}

// ---------------------------------------------------------------------------
// Section primitives
// ---------------------------------------------------------------------------

function SectionHeader({
  id,
  title,
  description,
}: {
  id: string;
  title: string;
  description?: string;
}) {
  return (
    <div id={id} className="scroll-mt-20">
      <h2 className="font-semibold text-foreground text-xs uppercase tracking-[0.18em]">
        {title}
      </h2>
      {description && (
        <p className="mt-1 text-muted-foreground text-sm">{description}</p>
      )}
    </div>
  );
}

function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="font-medium text-foreground text-sm">{label}</span>
      <div className="mt-1.5">{children}</div>
      {hint && <p className="mt-1 text-muted-foreground text-xs">{hint}</p>}
    </label>
  );
}

function Banner({
  kind,
  children,
}: {
  kind: "ok" | "error";
  children: React.ReactNode;
}) {
  const ok = kind === "ok";
  return (
    <div
      className={
        ok
          ? "flex items-start gap-2 rounded-md border border-green-500/30 bg-green-500/10 p-3 text-green-700 text-sm dark:text-green-300"
          : "flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-destructive text-sm"
      }
    >
      {ok ? (
        <CheckIcon className="mt-0.5 size-4 shrink-0" />
      ) : (
        <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
      )}
      <span>{children}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

function ProfileSection() {
  const { user, setUser } = useAuth();
  const [fullName, setFullName] = useState(user.full_name);
  const [email, setEmail] = useState(user.email);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const dirty =
    fullName !== user.full_name || email.trim() !== user.email;

  const onSave = async () => {
    setSaving(true);
    setMsg(null);
    setErr(null);
    try {
      const updated = await updateProfile({
        full_name: fullName,
        email: email.trim().toLowerCase(),
      });
      setUser(updated as AuthUser);
      setFullName(updated.full_name);
      setEmail(updated.email);
      setMsg("Profile updated.");
    } catch (e) {
      setErr(
        e instanceof AccountError ? e.detail : "Failed to update profile.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader
        id="profile"
        title="Profile"
        description="How you appear in the app and where we'll reach you."
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Display name">
          <Input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Your name"
          />
        </Field>
        <Field label="Login email" hint="Used to sign in.">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
          />
        </Field>
      </div>
      {msg && <Banner kind="ok">{msg}</Banner>}
      {err && <Banner kind="error">{err}</Banner>}
      <div className="flex items-center gap-3">
        <Button onClick={onSave} disabled={!dirty || saving}>
          {saving && <Loader2Icon className="size-3.5 animate-spin" />}
          Save changes
        </Button>
        <span className="text-muted-foreground text-xs">
          Tier · <span className="font-semibold">{user.tier}</span>
        </span>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Password
// ---------------------------------------------------------------------------

function PasswordSection() {
  const [curPw, setCurPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const onSave = async () => {
    setSaving(true);
    setMsg(null);
    setErr(null);
    try {
      await changePassword({
        current_password: curPw,
        new_password: newPw,
      });
      setCurPw("");
      setNewPw("");
      setMsg("Password updated.");
    } catch (e) {
      setErr(
        e instanceof AccountError ? e.detail : "Failed to change password.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader
        id="password"
        title="Password"
        description="Use at least 8 characters. We don't enforce more — pick something memorable."
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Current password">
          <Input
            type="password"
            value={curPw}
            onChange={(e) => setCurPw(e.target.value)}
            autoComplete="current-password"
          />
        </Field>
        <Field label="New password">
          <Input
            type="password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            autoComplete="new-password"
          />
        </Field>
      </div>
      {msg && <Banner kind="ok">{msg}</Banner>}
      {err && <Banner kind="error">{err}</Banner>}
      <div>
        <Button
          onClick={onSave}
          disabled={saving || !curPw || newPw.length < 8}
        >
          {saving && <Loader2Icon className="size-3.5 animate-spin" />}
          Update password
        </Button>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// API Keys
// ---------------------------------------------------------------------------

function ApiKeysSection() {
  const [keys, setKeys] = useState<APIKey[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [justCreated, setJustCreated] = useState<CreatedAPIKey | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<APIKey | null>(null);
  const [copied, setCopied] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await listKeys();
      setKeys(data);
    } catch (e) {
      setError(e instanceof AccountError ? e.detail : "Failed to load keys.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onCreate = async () => {
    if (!name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createKey(name.trim());
      setJustCreated(created);
      setName("");
      await refresh();
    } catch (e) {
      setError(e instanceof AccountError ? e.detail : "Failed to create key.");
    } finally {
      setCreating(false);
    }
  };

  const onRevoke = async () => {
    if (!confirmRevoke) return;
    try {
      await revokeKey(confirmRevoke.id);
      setConfirmRevoke(null);
      await refresh();
    } catch (e) {
      setError(e instanceof AccountError ? e.detail : "Failed to revoke key.");
    }
  };

  const onCopyRaw = async () => {
    if (!justCreated) return;
    await navigator.clipboard.writeText(justCreated.raw_key);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader
        id="api-keys"
        title="API keys"
        description="One key per integration. We only show the raw key once at creation — store it somewhere safe."
      />

      {justCreated && (
        <div className="rounded-lg border border-primary/40 bg-primary/5 p-4">
          <div className="flex items-baseline justify-between gap-3">
            <div>
              <h3 className="font-semibold text-foreground text-sm">
                New key — copy it now
              </h3>
              <p className="mt-1 text-muted-foreground text-xs">
                This is the only time you'll see the full secret. We store
                only the prefix on our side.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setJustCreated(null)}
              className="text-muted-foreground text-xs hover:text-foreground"
            >
              Dismiss
            </button>
          </div>
          <div className="mt-3 flex items-center gap-2 rounded-md border bg-background px-3 py-2 font-mono text-xs">
            <span className="min-w-0 flex-1 truncate">
              {justCreated.raw_key}
            </span>
            <Button
              size="sm"
              variant="outline"
              onClick={onCopyRaw}
              className="shrink-0"
            >
              {copied ? (
                <CheckIcon className="size-3.5" />
              ) : (
                <CopyIcon className="size-3.5" />
              )}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <Field label="Key label">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Claude Desktop on laptop"
          />
        </Field>
        <Button onClick={onCreate} disabled={creating || !name.trim()}>
          {creating ? (
            <Loader2Icon className="size-3.5 animate-spin" />
          ) : (
            <PlusIcon className="size-3.5" />
          )}
          Create key
        </Button>
      </div>

      {error && <Banner kind="error">{error}</Banner>}

      {keys === null ? (
        <div className="flex items-center gap-2 text-muted-foreground text-sm">
          <Loader2Icon className="size-3.5 animate-spin" /> Loading keys…
        </div>
      ) : keys.length === 0 ? (
        <div className="rounded-md border border-dashed bg-muted/30 px-4 py-8 text-center text-muted-foreground text-sm">
          No keys yet. Create one above to integrate with the MCP server.
        </div>
      ) : (
        <ul className="divide-y border-y">
          {keys.map((k) => (
            <li
              key={k.id}
              className="flex items-baseline gap-4 py-3 text-sm"
            >
              <span className="w-44 shrink-0 truncate font-medium">
                {k.name}
              </span>
              <span className="w-32 shrink-0 font-mono text-muted-foreground text-xs">
                {k.prefix}…
              </span>
              <span className="hidden flex-1 text-muted-foreground text-xs md:block">
                Created {fmtDate(k.created_at)} · Last used{" "}
                {fmtDateTime(k.last_used_at)}
              </span>
              <button
                type="button"
                onClick={() => setConfirmRevoke(k)}
                className="ml-auto shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                aria-label={`Revoke ${k.name}`}
              >
                <TrashIcon className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <Dialog
        open={confirmRevoke !== null}
        onOpenChange={(open) => !open && setConfirmRevoke(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke this key?</DialogTitle>
            <DialogDescription>
              Anything currently using{" "}
              <span className="font-mono">{confirmRevoke?.prefix}…</span> (
              {confirmRevoke?.name}) will start getting 401s immediately.
              This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmRevoke(null)}
            >
              Cancel
            </Button>
            <Button
              onClick={onRevoke}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Revoke key
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

// ---------------------------------------------------------------------------
// MCP config
// ---------------------------------------------------------------------------

const PATH_FALLBACK = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin";

function claudeDesktopSnippet(rawKey: string, mcpHost: string) {
  return JSON.stringify(
    {
      mcpServers: {
        "iowa-legal-corpus": {
          command: "npx",
          args: [
            "-y",
            "mcp-remote",
            mcpHost,
            "--header",
            "X-API-Key:${IOWA_LEGAL_CORPUS_KEY}",
          ],
          env: {
            IOWA_LEGAL_CORPUS_KEY: rawKey,
            PATH: PATH_FALLBACK,
          },
        },
      },
    },
    null,
    2,
  );
}

function McpConfigSection() {
  const [mcpHost, setMcpHost] = useState<string>(
    "https://your-host.example.com/mcp",
  );
  const [mcpSource, setMcpSource] = useState<
    "explicit" | "codespaces" | "unset"
  >("unset");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchPublicConfig()
      .then((cfg) => {
        if (cancelled) return;
        if (cfg.mcp_host) setMcpHost(cfg.mcp_host);
        setMcpSource(cfg.source);
      })
      .catch(() => {
        /* leave the placeholder host */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const snippet = useMemo(
    () => claudeDesktopSnippet("YOUR_RAW_KEY", mcpHost),
    [mcpHost],
  );

  const onCopy = async () => {
    await navigator.clipboard.writeText(snippet);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader
        id="mcp"
        title="MCP config"
        description="Drop this into Claude Desktop or Cursor to give your AI tools live access to the Iowa Legal Corpus via your API key."
      />

      <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
        <Field
          label="MCP host"
          hint={
            mcpSource === "explicit"
              ? "Pinned by the server's public config."
              : mcpSource === "codespaces"
                ? "Auto-detected from the running Codespace."
                : "We couldn't auto-detect a host — set MCP_HOST on the server or edit the snippet below."
          }
        >
          <Input
            value={mcpHost}
            onChange={(e) => setMcpHost(e.target.value)}
          />
        </Field>
        <Button variant="outline" onClick={onCopy}>
          {copied ? (
            <CheckIcon className="size-3.5" />
          ) : (
            <CopyIcon className="size-3.5" />
          )}
          {copied ? "Copied" : "Copy snippet"}
        </Button>
      </div>

      <pre className="max-h-96 overflow-auto rounded-lg border bg-muted/40 p-4 text-xs leading-relaxed">
        <code>{snippet}</code>
      </pre>

      <div className="rounded-md border bg-muted/20 p-4 text-muted-foreground text-sm">
        <p>
          Replace{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
            YOUR_RAW_KEY
          </code>{" "}
          with a key you create above. Then drop the snippet into
          Claude Desktop&apos;s{" "}
          <code className="font-mono text-xs">claude_desktop_config.json</code>{" "}
          (or your MCP client&apos;s equivalent) and restart the app.
        </p>
        <p className="mt-2">
          Why <code className="font-mono text-xs">mcp-remote</code>? Claude
          Desktop only knows how to spawn local stdio subprocesses;{" "}
          <code className="font-mono text-xs">mcp-remote</code> is a tiny shim
          that bridges to our streamable HTTP transport, attaching the{" "}
          <code className="font-mono text-xs">X-API-Key</code> header on every
          request.
        </p>
      </div>
    </section>
  );
}
