"use client";

// Shared sign-in / register form logic — one brain for every sign-in skin.
// The legacy gate (components/auth-gate.tsx SignInScreen) and the Carbon v2
// sign-in (components/carbon/sign-in.tsx) both render on top of this hook, so
// auth behavior can't drift between the two UIs while v2 is built out.

import { type FormEvent, useState } from "react";
import type { AuthUser } from "@/components/auth-gate";
import { csrfHeaders } from "@/lib/csrf";

export type AuthMode = "login" | "register";

export function useCredentialsForm(onSignedIn: (u: AuthUser) => void) {
	const [mode, setMode] = useState<AuthMode>("login");
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
		try {
			const path =
				mode === "register" ? "/api/auth/register" : "/api/auth/login";
			const body =
				mode === "register"
					? { email: email.trim().toLowerCase(), password, full_name: fullName }
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
