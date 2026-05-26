"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Loader2Icon,
  LayersIcon,
  ScrollTextIcon,
  ShieldCheckIcon,
  type LucideIcon,
} from "lucide-react";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export type AuthUser = {
  id: number;
  email: string;
  full_name: string;
  tier: string;
};

type AuthContextValue = {
  user: AuthUser;
  signOut: () => Promise<void>;
  // Apply a freshly-fetched user (e.g. after a profile PATCH) to the
  // context so the sidebar avatar / welcome name update without a reload.
  setUser: (u: AuthUser) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** Read the current signed-in user. Safe to call anywhere inside <AuthGate>. */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth() must be used inside <AuthGate>");
  }
  return ctx;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<"checking" | "signed-in" | "signed-out">(
    "checking",
  );
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/auth/me", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((u: AuthUser | null) => {
        if (cancelled) return;
        if (u) {
          setUser(u);
          setStatus("signed-in");
        } else {
          setStatus("signed-out");
        }
      })
      .catch(() => !cancelled && setStatus("signed-out"));
    return () => {
      cancelled = true;
    };
  }, []);

  const signOut = useCallback(async () => {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "include",
    });
    setStatus("signed-out");
    setUser(null);
  }, []);

  if (status === "checking") {
    return (
      <div className="flex h-dvh items-center justify-center text-muted-foreground text-sm">
        Checking session…
      </div>
    );
  }

  if (status === "signed-out") {
    return (
      <SignInScreen
        onSignedIn={(u) => {
          setUser(u);
          setStatus("signed-in");
        }}
      />
    );
  }

  return (
    <AuthContext.Provider value={{ user: user!, signOut, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Sign-in / register screen — split layout mirroring the original Vite app
// ---------------------------------------------------------------------------

type Mode = "login" | "register";

type Feature = { icon: LucideIcon; title: string; body: string };

const FEATURES: Feature[] = [
  {
    icon: ShieldCheckIcon,
    title: "Reviewed & grounded",
    body: "Every answer is traced to the currently effective, human-reviewed text.",
  },
  {
    icon: ScrollTextIcon,
    title: "Full citations",
    body: "Citation, effective date, and enacting session law on every provision.",
  },
  {
    icon: LayersIcon,
    title: "Hybrid search",
    body: "FTS + pg_trgm + pgvector embeddings fused with Reciprocal Rank Fusion.",
  },
];

function SignInScreen({ onSignedIn }: { onSignedIn: (u: AuthUser) => void }) {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const path = mode === "register" ? "/api/auth/register" : "/api/auth/login";
      const body =
        mode === "register"
          ? { email: email.trim().toLowerCase(), password, full_name: fullName }
          : { email: email.trim().toLowerCase(), password };
      const r = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const detail = await r
          .json()
          .then((j: { detail?: string }) => j.detail)
          .catch(() => null);
        throw new Error(
          detail ||
            (mode === "register"
              ? `Registration failed (${r.status})`
              : `Login failed (${r.status})`),
        );
      }
      const u = (await r.json()) as AuthUser;
      onSignedIn(u);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const title = mode === "register" ? "Create your account" : "Sign in";
  const cta = mode === "register" ? "Create account" : "Sign in";
  const subhead =
    mode === "register"
      ? "Get an API key to use the Iowa Legal Corpus from Claude Desktop or your own integration."
      : "Sign in to chat with the Iowa Code and Court Rules.";
  const otherLabel =
    mode === "register"
      ? "Already have an account? Sign in"
      : "New here? Create an account";

  return (
    <div className="grid h-dvh w-full grid-cols-1 bg-background text-foreground md:grid-cols-2 lg:grid-cols-[1.05fr_1fr]">
      {/* Left — branded panel */}
      <div
        className="relative hidden flex-col justify-between overflow-hidden px-8 py-8 text-white md:flex md:px-12 md:py-12"
        style={{
          backgroundColor: "#1f3a5f",
          backgroundImage: "url(/login-bg.webp)",
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        {/* Gradient scrim so copy stays legible over any photo. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "linear-gradient(135deg, rgba(31,58,95,0.95) 0%, rgba(31,58,95,0.80) 45%, rgba(15,29,48,0.60) 100%)",
          }}
        />

        <div className="relative">
          <span className="font-semibold text-[11px] tracking-[0.18em] uppercase text-white/70">
            Hudson Legal Tech
          </span>
        </div>

        <div className="relative max-w-md">
          {/* Black banner block, same treatment as the corpus reader. */}
          <div className="mb-6 inline-block bg-black px-5 py-3 text-white">
            <div className="font-bold text-2xl leading-tight tracking-[0.04em] uppercase md:text-3xl">
              Iowa Statutes
              <br />& Court Rules
            </div>
          </div>

          <p className="mb-7 max-w-sm text-base leading-relaxed text-white/90">
            A grounded, citable interface to the Iowa Code and Court Rules —
            built for practitioners who need the effective text, not a guess.
          </p>

          <ul className="space-y-4">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <li key={f.title} className="flex items-start gap-3">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-full border border-white/25 bg-white/10">
                    <Icon className="size-4 text-white" />
                  </div>
                  <div>
                    <div className="font-semibold text-[15px] text-white">
                      {f.title}
                    </div>
                    <div className="mt-0.5 text-[13px] leading-relaxed text-white/75">
                      {f.body}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>

        <p className="relative text-[12px] text-white/60">
          Sourced from legis.iowa.gov · Not a substitute for the official
          publication.
        </p>
      </div>

      {/* Right — form */}
      <div className="flex items-center justify-center overflow-y-auto px-4 py-10 sm:px-10">
        <div className="w-full max-w-sm">
          <div className="mb-1 font-semibold text-[11px] tracking-[0.18em] uppercase text-muted-foreground md:hidden">
            Hudson Legal Tech
          </div>
          <h1 className="font-bold text-2xl tracking-tight text-foreground">
            {title}
          </h1>
          <p className="mt-1.5 text-muted-foreground text-sm">{subhead}</p>

          {error && (
            <div className="mt-5 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-destructive text-sm">
              {error}
            </div>
          )}

          <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
            {mode === "register" && (
              <label className="block">
                <span className="font-medium text-sm">
                  Full name{" "}
                  <span className="text-muted-foreground text-xs">
                    (optional)
                  </span>
                </span>
                <Input
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  disabled={busy}
                  autoComplete="name"
                  className="mt-1.5"
                />
              </label>
            )}
            <label className="block">
              <span className="font-medium text-sm">Email</span>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={busy}
                autoComplete={mode === "register" ? "email" : "username"}
                className="mt-1.5"
              />
            </label>
            <label className="block">
              <span className="font-medium text-sm">Password</span>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={busy}
                autoComplete={
                  mode === "register" ? "new-password" : "current-password"
                }
                className="mt-1.5"
              />
              {mode === "register" && (
                <p className="mt-1 text-muted-foreground text-xs">
                  At least 8 characters.
                </p>
              )}
            </label>

            <Button
              type="submit"
              disabled={busy}
              size="lg"
              className="mt-2 w-full"
            >
              {busy && <Loader2Icon className="size-4 animate-spin" />}
              {busy ? "Working…" : cta}
            </Button>

            <button
              type="button"
              onClick={() => {
                setError(null);
                setMode(mode === "register" ? "login" : "register");
              }}
              className="self-center text-primary text-sm underline-offset-2 hover:underline"
            >
              {otherLabel}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
