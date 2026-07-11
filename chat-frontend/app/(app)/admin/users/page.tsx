"use client";

// Admin · Users — staff-only account directory over /api/admin/users.
// Server-side search (debounced) + tier/status filters; the returned page is
// sorted client-side like the usage table. Unlike /admin/usage this lists
// EVERY account, including ones with no LLM activity, and each row links to
// the management detail page at /admin/users/[id].

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
	BtnGhost,
	Eyebrow,
	Notification,
	Panel,
	SelectField,
	Tag,
	type TagKind,
	TextField,
} from "@/components/carbon/primitives";
import { AccountError } from "@/lib/iowa-account";
import {
	type AdminUserRow,
	type AdminUserStatusFilter,
	getAdminUsers,
	type UsageUserStatus,
} from "@/lib/iowa-admin";
import { cn } from "@/lib/utils";
import { TIER_TAGS } from "./tags";

const fmtMoney = (n: number) => `$${n.toFixed(2)}`;

const MONTHS = [
	"Jan",
	"Feb",
	"Mar",
	"Apr",
	"May",
	"Jun",
	"Jul",
	"Aug",
	"Sep",
	"Oct",
	"Nov",
	"Dec",
];

// "2026-07-10T…" → "Jul 10, 2026". Parsed by hand so a date-only string
// never shifts a day through the local timezone.
function fmtDate(iso: string): string {
	const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
	if (!m) return iso;
	return `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}`;
}

const BUDGET_TAGS: Record<UsageUserStatus, { label: string; kind: TagKind }> = {
	ok: { label: "OK", kind: "green" },
	near: { label: "Near cap", kind: "yellow" },
	capped: { label: "Capped", kind: "red" },
	exempt: { label: "Exempt", kind: "outline" },
};

const TIER_OPTIONS = [
	{ value: "", label: "All tiers" },
	{ value: "free", label: "Trial" },
	{ value: "solo", label: "Solo" },
	{ value: "firm", label: "Firm" },
	{ value: "custom", label: "Custom" },
];

const STATUS_OPTIONS = [
	{ value: "", label: "All accounts" },
	{ value: "active", label: "Active" },
	{ value: "deactivated", label: "Deactivated" },
	{ value: "staff", label: "Staff" },
];

const PAGE_SIZE = 100;

type SortKey =
	| "email"
	| "tier"
	| "state"
	| "month_cost_usd"
	| "active_api_keys"
	| "date_joined"
	| "last_login";

const COLS: { key: SortKey; label: string; numeric?: boolean }[] = [
	{ key: "email", label: "User" },
	{ key: "tier", label: "Tier" },
	{ key: "state", label: "Status" },
	{ key: "month_cost_usd", label: "Spend (MTD)", numeric: true },
	{ key: "active_api_keys", label: "API keys", numeric: true },
	{ key: "date_joined", label: "Joined", numeric: true },
	{ key: "last_login", label: "Last login", numeric: true },
];

export default function AdminUsersPage() {
	const [q, setQ] = useState("");
	const [debouncedQ, setDebouncedQ] = useState("");
	const [tier, setTier] = useState("");
	const [status, setStatus] = useState<AdminUserStatusFilter>("");
	const [offset, setOffset] = useState(0);
	const [rows, setRows] = useState<AdminUserRow[] | null>(null);
	const [total, setTotal] = useState(0);
	const [error, setError] = useState<Error | null>(null);
	const [fetching, setFetching] = useState(true);

	// Debounced search; a new query always restarts from the first page.
	useEffect(() => {
		const t = setTimeout(() => {
			setDebouncedQ(q.trim());
			setOffset(0);
		}, 300);
		return () => clearTimeout(t);
	}, [q]);

	useEffect(() => {
		let cancelled = false;
		setFetching(true);
		setError(null);
		getAdminUsers({
			q: debouncedQ,
			tier,
			status,
			limit: PAGE_SIZE,
			offset,
		})
			.then((r) => {
				if (cancelled) return;
				setRows(r.users);
				setTotal(r.total);
			})
			.catch((e) => !cancelled && setError(e as Error))
			.finally(() => !cancelled && setFetching(false));
		return () => {
			cancelled = true;
		};
	}, [debouncedQ, tier, status, offset]);

	const httpStatus = error instanceof AccountError ? error.status : null;
	const loaded = rows !== null;

	return (
		<div className="mx-auto w-full max-w-[1320px] px-5 py-10 sm:px-8">
			<header>
				<Eyebrow>Admin · User management</Eyebrow>
				<h1 className="mt-4 font-light text-3xl sm:text-4xl">Users</h1>
				<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
					Every registered account — tier, budget, and access controls. Select a
					user to manage their account.
				</p>
			</header>

			{httpStatus === 401 ? (
				<Notification
					kind="error"
					title="Staff only"
					className="mt-10 max-w-xl"
					action={
						<BtnGhost onClick={() => window.location.reload()}>
							Sign in
						</BtnGhost>
					}
				>
					You need an active staff session to view this page.
				</Notification>
			) : error && !loaded ? (
				<Notification
					kind="error"
					title="Couldn't load users"
					className="mt-10 max-w-xl"
				>
					{error.message}
				</Notification>
			) : !loaded ? (
				<p className="mt-10 text-[var(--cds-text-2)] text-sm">Loading users…</p>
			) : (
				<div
					className={cn(
						"mt-8 transition-opacity",
						fetching && "pointer-events-none opacity-60",
					)}
				>
					{error && (
						<Notification
							kind="error"
							title="Couldn't refresh"
							className="mb-6"
						>
							{error.message}
						</Notification>
					)}
					<div className="mb-6 flex flex-wrap items-end gap-x-4 gap-y-3">
						<TextField
							label="Search"
							type="search"
							placeholder="Email or name…"
							value={q}
							onChange={(e) => setQ(e.target.value)}
							className="w-64"
						/>
						<SelectField
							label="Tier"
							value={tier}
							onChange={(e) => {
								setTier(e.target.value);
								setOffset(0);
							}}
							options={TIER_OPTIONS}
							className="w-40"
						/>
						<SelectField
							label="Status"
							value={status}
							onChange={(e) => {
								setStatus(e.target.value as AdminUserStatusFilter);
								setOffset(0);
							}}
							options={STATUS_OPTIONS}
							className="w-44"
						/>
					</div>
					<UsersTable rows={rows} total={total} />
					{total > PAGE_SIZE && (
						<div className="mt-4 flex items-center justify-between text-[var(--cds-text-2)] text-xs">
							<span>
								Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of{" "}
								{total}
							</span>
							<span className="flex gap-2">
								<BtnGhost
									size="md"
									disabled={offset === 0}
									onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
								>
									← Previous
								</BtnGhost>
								<BtnGhost
									size="md"
									disabled={offset + PAGE_SIZE >= total}
									onClick={() => setOffset(offset + PAGE_SIZE)}
								>
									Next →
								</BtnGhost>
							</span>
						</div>
					)}
				</div>
			)}
		</div>
	);
}

function UsersTable({ rows, total }: { rows: AdminUserRow[]; total: number }) {
	const [sortKey, setSortKey] = useState<SortKey>("email");
	const [sortDir, setSortDir] = useState<1 | -1>(1);

	const sorted = useMemo(() => {
		const val = (u: AdminUserRow): string | number => {
			switch (sortKey) {
				case "email":
					return u.email.toLowerCase();
				case "tier":
					return u.is_staff ? "zz-staff" : u.tier;
				case "state":
					return u.is_active ? 0 : 1;
				case "last_login":
					return u.last_login ?? "";
				case "date_joined":
					return u.date_joined;
				default:
					return u[sortKey];
			}
		};
		return [...rows].sort((a, b) => {
			const ka = val(a);
			const kb = val(b);
			const c =
				typeof ka === "string" ? ka.localeCompare(String(kb)) : ka - Number(kb);
			return c * sortDir;
		});
	}, [rows, sortKey, sortDir]);

	const onSort = (c: (typeof COLS)[number]) => {
		if (c.key === sortKey) {
			setSortDir((d) => (d === 1 ? -1 : 1));
		} else {
			setSortKey(c.key);
			setSortDir(c.numeric ? -1 : 1);
		}
	};

	return (
		<Panel
			title={`All users — ${total} account${total === 1 ? "" : "s"}`}
			action={
				<span className="font-mono text-[11px] text-[var(--cds-helper)]">
					click a column to sort
				</span>
			}
		>
			<div className="overflow-x-auto">
				<table className="w-full min-w-[860px] border-collapse text-left">
					<thead>
						<tr>
							{COLS.map((c) => (
								<th
									key={c.key}
									aria-sort={
										sortKey === c.key
											? sortDir === -1
												? "descending"
												: "ascending"
											: undefined
									}
									className="border-[var(--cds-border-strong)] border-b bg-[var(--cds-layer)] p-0"
								>
									<button
										type="button"
										onClick={() => onSort(c)}
										className={cn(
											"flex w-full items-center gap-1 whitespace-nowrap px-3 py-2.5 font-mono font-normal text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.1em] transition-colors hover:text-[var(--cds-text)]",
											c.numeric && "justify-end",
										)}
									>
										{c.label}
										{sortKey === c.key && (
											<span className="text-[var(--cds-link)]">
												{sortDir === -1 ? "▾" : "▴"}
											</span>
										)}
									</button>
								</th>
							))}
						</tr>
					</thead>
					<tbody>
						{sorted.length === 0 ? (
							<tr>
								<td
									colSpan={COLS.length}
									className="px-3 py-6 text-center text-[var(--cds-text-2)] text-sm"
								>
									No users match those filters.
								</td>
							</tr>
						) : (
							sorted.map((u) => {
								const tier = u.is_staff
									? { label: "Staff", kind: "outline" as TagKind }
									: (TIER_TAGS[u.tier] ?? {
											label: u.tier,
											kind: "gray" as TagKind,
										});
								const budget = BUDGET_TAGS[u.budget_status];
								return (
									<tr
										key={u.id}
										className="border-[var(--cds-border)] border-b transition-colors hover:bg-[var(--cds-layer)]"
									>
										<td className="whitespace-nowrap px-3 py-2.5">
											<Link
												href={`/admin/users/${u.id}`}
												className="group block"
											>
												<p className="text-[13px] text-[var(--cds-link)] group-hover:underline">
													{u.email}
												</p>
												{u.name && (
													<p className="text-[var(--cds-helper)] text-xs">
														{u.name}
													</p>
												)}
											</Link>
										</td>
										<td className="whitespace-nowrap px-3 py-2.5">
											<Tag kind={tier.kind}>{tier.label}</Tag>
										</td>
										<td className="whitespace-nowrap px-3 py-2.5">
											{u.is_active ? (
												<Tag kind="green">Active</Tag>
											) : (
												<Tag kind="red">Deactivated</Tag>
											)}
										</td>
										<td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[13px] tabular-nums">
											{fmtMoney(u.month_cost_usd)}
											{u.budget_status !== "exempt" && (
												<Tag kind={budget.kind} className="ml-2">
													{budget.label}
												</Tag>
											)}
										</td>
										<td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[13px] tabular-nums">
											{u.active_api_keys || "—"}
										</td>
										<td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[13px] text-[var(--cds-text-2)] tabular-nums">
											{fmtDate(u.date_joined)}
										</td>
										<td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[13px] text-[var(--cds-text-2)] tabular-nums">
											{u.last_login ? fmtDate(u.last_login) : "never"}
										</td>
									</tr>
								);
							})
						)}
					</tbody>
				</table>
			</div>
		</Panel>
	);
}
