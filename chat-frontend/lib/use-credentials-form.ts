"use client";

// Shared sign-in / register form logic — one brain for every sign-in skin.
// The legacy gate (components/auth-gate.tsx SignInScreen) and the Carbon v2
// sign-in (components/carbon/sign-in.tsx) both render on top of this hook, so
// auth behavior can't drift between the two UIs while v2 is built out.

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import type { AuthUser } from "@/components/auth-gate";
import { csrfHeaders } from "@/lib/csrf";

export type AuthMode = "login" | "register";

// An org invitation link (/invite/<token>) sends signed-out visitors to the
// sign-in gate as /?invite=<token>. Registering carries the token to the server,
// which accepts the invitation in the same transaction as the account creation;
// signing in to an existing account doesn't, so both paths get handed back to
// the invite page afterwards to finish and to see which org they joined.
// Read at submit time (never during render) so there's nothing to hydrate.
function inviteFromUrl(): string | null {
	if (typeof window === "undefined") return null;
	const token = new URLSearchParams(window.location.search).get("invite");
	return token?.trim() ? token : null;
}

export function useCredentialsForm(
	onSignedIn: (u: AuthUser) => void,
	// The sign-in gate opens on "login"; the /start signup wizard opens on
	// "register" — same brain, different first screen.
	initialMode: AuthMode = "login",
) {
	const router = useRouter();
	const [mode, setMode] = useState<AuthMode>(initialMode);
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [fullName, setFullName] = useState("");
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const toggleMode = () => {
		setError(null);
		setMode(mode === "register" ? "login" : "register");
	};

	const onSubmit = async (e: FormEvent) => {
		e.preventDefault();
		setBusy(true);
		setError(null);
		const invite = inviteFromUrl();
		try {
			const path =
				mode === "register" ? "/api/auth/register" : "/api/auth/login";
			const body =
				mode === "register"
					? {
							email: email.trim().toLowerCase(),
							password,
							full_name: fullName,
							...(invite ? { invite } : {}),
						}
					: { email: email.trim().toLowerCase(), password };
			const r = await fetch(path, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					...(await csrfHeaders()),
				},
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
			if (invite) router.replace(`/invite/${encodeURIComponent(invite)}`);
		} catch (err) {
			setError((err as Error).message);
		} finally {
			setBusy(false);
		}
	};

	return {
		mode,
		toggleMode,
		email,
		setEmail,
		password,
		setPassword,
		fullName,
		setFullName,
		busy,
		error,
		onSubmit,
	};
}
