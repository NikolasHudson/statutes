"use client";

// Admin · Usage & spend — staff-only dashboard over /api/admin/usage/*.
// Layout mirrors the approved mockup: filter bar (server-side feature/model
// filters + client-side email search), KPI tile row, tokens-per-day stacked
// bar chart (pure divs, hover tooltip, 7/30/90-day tabs), spend-by-feature
// bars + model breakdown, and a sortable per-user table with budget meters.
// Series colors are contrast/CVD-validated per theme: prompt teal #009d9a
// in both, completion #0f62fe (light) / #4589ff (dark).

import { useEffect, useMemo, useState } from "react";
import {
	BLUE,
	BtnGhost,
	Eyebrow,
	KVList,
	LineTabs,
	Notification,
	Panel,
	SelectField,
	Tag,
	type TagKind,
	TextField,
	type ThemeName,
	useTheme,
} from "@/components/carbon/primitives";
import { AccountError } from "@/lib/iowa-account";
import {
	getUsageDaily,
	getUsageFilters,
	getUsageSummary,
	getUsageUsers,
	type UsageDay,
	type UsageFilterOptions,
	type UsageRange,
	type UsageSummary,
	type UsageTier,
	type UsageUser,
	type UsageUserStatus,
} from "@/lib/iowa-admin";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

function fmtTok(n: number): string {
	if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
	if (n >= 1e3) return `${Math.round(n / 1e3)}K`;
	return String(Math.round(n));
}

const fmtMoney = (n: number) => `$${n.toFixed(2)}`;
const fmtInt = (n: number) => n.toLocaleString("en-US");

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

// "2026-07-10" → "Jul 10". Parsed by hand so a date-only string never shifts
// a day through the local timezone.
function fmtDay(iso: string): string {
	const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
	if (!m) return iso;
	return `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}`;
}

function median(nums: number[]): number | null {
	if (nums.length === 0) return null;
	const s = [...nums].sort((a, b) => a - b);
	const mid = Math.floor(s.length / 2);
	return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

// Round a chart maximum up to a "nice" number (1/2/2.5/5 × 10^k) so the
// gridline labels come out clean.
function niceCeil(n: number): number {
	if (n <= 0) return 0;
	const p = 10 ** Math.floor(Math.log10(n));
	const m = n / p;
	const nice = m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10;
	return nice * p;
}

// ---------------------------------------------------------------------------
// Chart series colors — validated for contrast + CVD per theme
// ---------------------------------------------------------------------------

const SERIES: Record<ThemeName, { prompt: string; completion: string }> = {
	white: { prompt: "#009d9a", completion: "#0f62fe" },
	g100: { prompt: "#009d9a", completion: "#4589ff" },
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const RANGE_TABS = [
	{ id: "7", label: "7 days" },
	{ id: "30", label: "30 days" },
	{ id: "90", label: "90 days" },
] as const;

type RangeId = (typeof RANGE_TABS)[number]["id"];

export default function AdminUsagePage() {
	const [range, setRange] = useState<UsageRange>(30);
	const [feature, setFeature] = useState(""); // "" = all features
	const [model, setModel] = useState(""); // "" = all models
	const [emailQuery, setEmailQuery] = useState("");
	const [filterOpts, setFilterOpts] = useState<UsageFilterOptions | null>(null);
	const [summary, setSummary] = useState<UsageSummary | null>(null);
	const [daily, setDaily] = useState<UsageDay[] | null>(null);
	const [users, setUsers] = useState<UsageUser[] | null>(null);
	const [error, setError] = useState<Error | null>(null);
	const [fetching, setFetching] = useState(true);

	useEffect(() => {
		let cancelled = false;
		setFetching(true);
		setError(null);
		const filter = {
			feature: feature || undefined,
			model: model || undefined,
		};
		Promise.all([
			getUsageSummary(range, filter),
			getUsageDaily(range, filter),
			getUsageUsers(range, filter),
		])
			.then(([s, d, u]) => {
				if (cancelled) return;
				setSummary(s);
				setDaily(d.days);
				setUsers(u.users);
			})
			.catch((e) => !cancelled && setError(e as Error))
			.finally(() => !cancelled && setFetching(false));
		return () => {
			cancelled = true;
		};
	}, [range, feature, model]);

	// Dropdown options — all-time distinct values, fetched once. A failure
	// here just leaves the selects on "All …"; the main auth errors surface
	// through the usage fetch above.
	useEffect(() => {
		let cancelled = false;
		getUsageFilters()
			.then((f) => !cancelled && setFilterOpts(f))
			.catch(() => {});
		return () => {
			cancelled = true;
		};
	}, []);

	const status = error instanceof AccountError ? error.status : null;
	const loaded = summary !== null && daily !== null && users !== null;
	const filterActive = feature !== "" || model !== "";

	return (
		<div className="mx-auto w-full max-w-[1320px] px-5 py-10 sm:px-8">
			<div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-6">
				<header>
					<Eyebrow>Admin · Platform usage</Eyebrow>
					<h1 className="mt-4 font-light text-3xl sm:text-4xl">
						Usage &amp; spend
					</h1>
					<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
						Token consumption, LLM cost, and per-user budgets across chat,
						verification, and the email assistant.
					</p>
				</header>
				<LineTabs<RangeId>
					tabs={[...RANGE_TABS]}
					value={String(range) as RangeId}
					onChange={(id) => setRange(Number(id) as UsageRange)}
				/>
			</div>

			{status === 403 ? (
				<Notification
					kind="error"
					title="Staff only"
					className="mt-10 max-w-xl"
				>
					You need staff access to view this page.
				</Notification>
			) : status === 401 ? (
				<Notification
					kind="error"
					title="Session expired"
					className="mt-10 max-w-xl"
					action={
						<BtnGhost onClick={() => window.location.reload()}>
							Sign in
						</BtnGhost>
					}
				>
					You&rsquo;ve been signed out. Sign in again to view usage.
				</Notification>
			) : error && !loaded ? (
				<Notification
					kind="error"
					title="Couldn't load usage"
					className="mt-10 max-w-xl"
				>
					{error.message}
				</Notification>
			) : !loaded ? (
				<p className="mt-10 text-[var(--cds-text-2)] text-sm">Loading usage…</p>
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
					<FilterBar
						options={filterOpts}
						feature={feature}
						onFeature={setFeature}
						model={model}
						onModel={setModel}
						emailQuery={emailQuery}
						onEmailQuery={setEmailQuery}
						className="mb-6"
					/>
					<KpiRow summary={summary} users={users} />
					<div className="mt-6 grid gap-6 xl:grid-cols-[2fr_1fr]">
						<TokensChart days={daily} range={range} />
						<FeaturePanel summary={summary} range={range} />
					</div>
					<UsersPanel
						users={users}
						range={range}
						emailQuery={emailQuery}
						filterActive={filterActive}
						className="mt-6"
					/>
				</div>
			)}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Filter bar — server-side feature/model filters + client-side email search
// ---------------------------------------------------------------------------

// Display labels for feature slugs, shared by the feature dropdown and the
// spend-by-feature panel. Unknown slugs fall back to a prettified slug.
const FEATURE_LABELS: Record<string, string> = {
	chat: "Chat",
	email: "Email assistant",
	verification: "Verification",
	query_rewrite: "Query rewrite",
	applicability: "Applicability",
	web_currency: "Web currency",
	query_expansion: "Query expansion",
	embedding: "Embeddings",
	rerank: "Rerank",
	treatment: "Treatment (citator)",
	retrieval_judge: "Retrieval judge",
};

const featureLabel = (f: string) =>
	FEATURE_LABELS[f] ??
	f.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function FilterBar({
	options,
	feature,
	onFeature,
	model,
	onModel,
	emailQuery,
	onEmailQuery,
	className,
}: {
	options: UsageFilterOptions | null;
	feature: string;
	onFeature: (f: string) => void;
	model: string;
	onModel: (m: string) => void;
	emailQuery: string;
	onEmailQuery: (q: string) => void;
	className?: string;
}) {
	// If /filters hasn't loaded (or dropped a value), keep the current
	// selection visible in its dropdown rather than silently blanking it.
	const features = options?.features ?? [];
	const models = options?.models ?? [];
	const featureOpts =
		feature && !features.includes(feature) ? [...features, feature] : features;
	const modelOpts =
		model && !models.includes(model) ? [...models, model] : models;

	return (
		<div className={cn("flex flex-wrap items-end gap-x-4 gap-y-3", className)}>
			<SelectField
				label="Feature"
				value={feature}
				onChange={(e) => onFeature(e.target.value)}
				options={[
					{ value: "", label: "All features" },
					...featureOpts.map((f) => ({ value: f, label: featureLabel(f) })),
				]}
				className="w-48"
			/>
			<SelectField
				label="Model"
				value={model}
				onChange={(e) => onModel(e.target.value)}
				options={[{ value: "", label: "All models" }, ...modelOpts]}
				className="w-56"
			/>
			<TextField
				label="User"
				type="search"
				placeholder="Filter by email…"
				value={emailQuery}
				onChange={(e) => onEmailQuery(e.target.value)}
				className="w-64"
			/>
			{(feature !== "" || model !== "") && (
				<div className="flex flex-wrap items-center gap-2 pb-2">
					{feature !== "" && (
						<FilterTag
							label={`feature: ${featureLabel(feature)}`}
							onClear={() => onFeature("")}
						/>
					)}
					{model !== "" && (
						<FilterTag label={`model: ${model}`} onClear={() => onModel("")} />
					)}
				</div>
			)}
		</div>
	);
}

function FilterTag({ label, onClear }: { label: string; onClear: () => void }) {
	return (
		<Tag kind="blue" className="pr-0">
			{label}
			<button
				type="button"
				aria-label={`Clear filter — ${label}`}
				onClick={onClear}
				className="flex h-full w-6 items-center justify-center transition-colors hover:bg-[#0f62fe]/20"
			>
				×
			</button>
		</Tag>
	);
}

// ---------------------------------------------------------------------------
// KPI tiles — hairline-gapped grid, mono tabular numbers
// ---------------------------------------------------------------------------

function KpiRow({
	summary,
	users,
}: {
	summary: UsageSummary;
	users: UsageUser[];
}) {
	const delta =
		summary.prev_cost_usd > 0
			? ((summary.cost_usd - summary.prev_cost_usd) / summary.prev_cost_usd) *
				100
			: null;
	const perUser =
		summary.active_users > 0 ? summary.cost_usd / summary.active_users : 0;
	const med = median(users.map((u) => u.cost_usd));

	const tiles: { k: string; v: string; d: string; dCls?: string }[] = [
		{
			k: "Tokens",
			v: fmtTok(summary.total_tokens),
			d: `last ${summary.days} days`,
		},
		{
			k: "LLM spend",
			v: fmtMoney(summary.cost_usd),
			d:
				delta === null
					? "no prior-period spend"
					: `${delta >= 0 ? "▲" : "▼"} ${Math.abs(delta).toFixed(0)}% vs prior period`,
			dCls:
				delta === null
					? undefined
					: delta >= 0
						? "text-[var(--cds-success-text)]"
						: "text-[var(--cds-danger-text)]",
		},
		{
			k: "Active users",
			v: fmtInt(summary.active_users),
			d: `of ${fmtInt(summary.registered_users)} registered`,
		},
		{
			k: "Chat turns",
			v: fmtInt(summary.turns),
			d: "incl. email assistant",
		},
		{
			k: "Cost / active user",
			v: fmtMoney(perUser),
			d: med === null ? "no per-user data" : `median ${fmtMoney(med)}`,
		},
	];

	return (
		<div className="grid grid-cols-2 gap-px border border-[var(--cds-border)] bg-[var(--cds-border)] lg:grid-cols-5">
			{tiles.map((t, i) => (
				<div
					key={t.k}
					className={cn(
						"flex min-h-28 flex-col bg-[var(--cds-bg)] p-4",
						// 5 tiles on a 2-col grid leave a hole — the last spans it.
						i === tiles.length - 1 && "col-span-2 lg:col-span-1",
					)}
				>
					<span className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.14em]">
						{t.k}
					</span>
					<span className="mt-auto pt-3 font-light font-mono text-3xl leading-tight tabular-nums">
						{t.v}
					</span>
					<span className={cn("mt-1 text-[var(--cds-text-2)] text-xs", t.dCls)}>
						{t.d}
					</span>
				</div>
			))}
		</div>
	);
}

// ---------------------------------------------------------------------------
// Tokens-per-day stacked bar chart — pure divs + a fixed-position tooltip
// ---------------------------------------------------------------------------

const CHART_H = 240; // px, matches h-60 on the plot area

function TokensChart({ days, range }: { days: UsageDay[]; range: UsageRange }) {
	const { theme } = useTheme();
	const colors = SERIES[theme];
	const [tip, setTip] = useState<{
		x: number;
		y: number;
		day: UsageDay;
	} | null>(null);

	const max = days.reduce(
		(m, d) => Math.max(m, d.prompt_tokens + d.completion_tokens),
		0,
	);
	const maxY = niceCeil(max);
	const empty = max === 0;
	const labelEvery = range === 7 ? 1 : range === 30 ? 5 : 15;

	return (
		<Panel
			title={`Tokens per day — last ${range} days`}
			action={
				<div className="flex items-center gap-4 text-[var(--cds-text-2)] text-xs">
					<span className="flex items-center gap-1.5">
						<span className="size-2.5" style={{ background: colors.prompt }} />
						Prompt
					</span>
					<span className="flex items-center gap-1.5">
						<span
							className="size-2.5"
							style={{ background: colors.completion }}
						/>
						Completion
					</span>
				</div>
			}
		>
			<div className="p-4">
				<div className="relative pt-2 pl-12">
					<div className="relative flex h-60 items-end gap-[2px] border-[var(--cds-border-strong)] border-b">
						{[0.25, 0.5, 0.75, 1].map((f) => (
							<div
								key={f}
								aria-hidden
								className="pointer-events-none absolute inset-x-0 border-[var(--cds-border)] border-t"
								style={{ bottom: f * CHART_H }}
							>
								<span className="-left-12 -top-2 absolute w-10 text-right font-mono text-[10px] text-[var(--cds-helper)] tabular-nums">
									{empty ? "" : fmtTok(maxY * f)}
								</span>
							</div>
						))}
						{days.map((d) => (
							<div
								key={d.date}
								// Hover reveals the tooltip; the same numbers are readable
								// from the aria-label (and the users table below).
								role="img"
								aria-label={`${fmtDay(d.date)}: ${fmtTok(d.prompt_tokens)} prompt, ${fmtTok(d.completion_tokens)} completion, ${fmtMoney(d.cost_usd)}`}
								className="flex h-full min-w-0 flex-1 flex-col justify-end gap-[2px] transition-opacity hover:opacity-80"
								onMouseMove={(e) =>
									setTip({ x: e.clientX, y: e.clientY, day: d })
								}
								onMouseLeave={() => setTip(null)}
							>
								{d.completion_tokens > 0 && (
									<div
										style={{
											height: Math.max(
												2,
												(d.completion_tokens / maxY) * CHART_H,
											),
											background: colors.completion,
										}}
									/>
								)}
								{d.prompt_tokens > 0 && (
									<div
										style={{
											height: Math.max(2, (d.prompt_tokens / maxY) * CHART_H),
											background: colors.prompt,
										}}
									/>
								)}
							</div>
						))}
						{empty && (
							<p className="absolute inset-x-0 top-24 text-center text-[var(--cds-text-2)] text-sm">
								No usage recorded yet
							</p>
						)}
					</div>
					<div className="flex gap-[2px] pt-1.5">
						{days.map((d, i) => (
							<span
								key={d.date}
								className="min-w-0 flex-1 whitespace-nowrap text-center font-mono text-[10px] text-[var(--cds-helper)]"
							>
								{i % labelEvery === 0 ? fmtDay(d.date) : ""}
							</span>
						))}
					</div>
				</div>
			</div>
			{tip && <ChartTip tip={tip} colors={colors} />}
		</Panel>
	);
}

function ChartTip({
	tip,
	colors,
}: {
	tip: { x: number; y: number; day: UsageDay };
	colors: { prompt: string; completion: string };
}) {
	const width = 192; // w-48
	const left = Math.min(
		tip.x + 14,
		(typeof window === "undefined" ? 1280 : window.innerWidth) - width - 8,
	);
	return (
		<div
			className="pointer-events-none fixed z-50 w-48 bg-[var(--cds-text)] px-3 py-2 text-[var(--cds-bg)] text-xs"
			style={{ left, top: tip.y + 14 }}
		>
			<p className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] opacity-70">
				{fmtDay(tip.day.date)}
			</p>
			<p className="flex items-center justify-between gap-4 tabular-nums">
				<span className="flex items-center gap-1.5">
					<span className="size-2" style={{ background: colors.prompt }} />
					Prompt
				</span>
				<span>{fmtTok(tip.day.prompt_tokens)}</span>
			</p>
			<p className="flex items-center justify-between gap-4 tabular-nums">
				<span className="flex items-center gap-1.5">
					<span className="size-2" style={{ background: colors.completion }} />
					Completion
				</span>
				<span>{fmtTok(tip.day.completion_tokens)}</span>
			</p>
			<p className="mt-1 flex items-center justify-between gap-4 tabular-nums">
				<span>Cost</span>
				<span>{fmtMoney(tip.day.cost_usd)}</span>
			</p>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Spend by feature + model breakdown
// ---------------------------------------------------------------------------

function FeaturePanel({
	summary,
	range,
}: {
	summary: UsageSummary;
	range: UsageRange;
}) {
	const { theme } = useTheme();
	const barColor = SERIES[theme].completion;
	const features = [...summary.features].sort(
		(a, b) => b.cost_usd - a.cost_usd,
	);
	const max = features[0]?.cost_usd ?? 0;

	return (
		<Panel title={`Spend by feature — ${range} days`}>
			<div className="p-4">
				{features.length === 0 ? (
					<p className="text-[var(--cds-text-2)] text-sm">
						No spend recorded yet.
					</p>
				) : (
					<div className="divide-y divide-[var(--cds-border)]">
						{features.map((f) => (
							<div
								key={f.feature}
								className="grid grid-cols-[minmax(0,7rem)_1fr_4rem] items-center gap-3 py-2"
							>
								<span className="truncate text-[13px] text-[var(--cds-text-2)]">
									{featureLabel(f.feature)}
								</span>
								<span className="h-3 bg-[var(--cds-layer)]">
									<span
										className="block h-full"
										style={{
											width: `${max > 0 ? (f.cost_usd / max) * 100 : 0}%`,
											background: barColor,
										}}
									/>
								</span>
								<span className="text-right font-mono text-xs tabular-nums">
									{fmtMoney(f.cost_usd)}
								</span>
							</div>
						))}
					</div>
				)}
			</div>
			{summary.models.length > 0 && (
				<div className="border-[var(--cds-border)] border-t">
					<KVList
						rows={summary.models.map(
							(m) =>
								[
									m.model,
									<span key={m.model} className="font-mono">
										{fmtTok(m.total_tokens)} tok · {fmtMoney(m.cost_usd)}
									</span>,
								] as const,
						)}
					/>
				</div>
			)}
		</Panel>
	);
}

// ---------------------------------------------------------------------------
// Per-user table — client-side sort, budget meters, status tags
// ---------------------------------------------------------------------------

const TIER_TAGS: Record<UsageTier, { label: string; kind: TagKind }> = {
	free: { label: "Trial", kind: "gray" },
	solo: { label: "Solo", kind: "blue" },
	firm: { label: "Firm", kind: "purple" },
	custom: { label: "Custom", kind: "gray" },
};

const STATUS_TAGS: Record<UsageUserStatus, { label: string; kind: TagKind }> = {
	ok: { label: "OK", kind: "green" },
	near: { label: "Near cap", kind: "yellow" },
	capped: { label: "Capped", kind: "red" },
	exempt: { label: "Exempt", kind: "outline" },
};

const STATUS_ORDER: Record<UsageUserStatus, number> = {
	exempt: 0,
	ok: 1,
	near: 2,
	capped: 3,
};

type SortKey =
	| "email"
	| "tier"
	| "turns"
	| "prompt_tokens"
	| "completion_tokens"
	| "cost_usd"
	| "budget"
	| "status"
	| "last_active";

const COLS: { key: SortKey; label: string; numeric?: boolean }[] = [
	{ key: "email", label: "User" },
	{ key: "tier", label: "Tier" },
	{ key: "turns", label: "Turns", numeric: true },
	{ key: "prompt_tokens", label: "Prompt tok", numeric: true },
	{ key: "completion_tokens", label: "Completion tok", numeric: true },
	{ key: "cost_usd", label: "Cost", numeric: true },
	{ key: "budget", label: "Budget used" },
	{ key: "status", label: "Status" },
	{ key: "last_active", label: "Last active", numeric: true },
];

const tierTag = (u: UsageUser) =>
	u.is_staff
		? { label: "Staff", kind: "outline" as TagKind }
		: (TIER_TAGS[u.tier] ?? { label: u.tier, kind: "gray" as TagKind });

function UsersPanel({
	users,
	range,
	emailQuery,
	filterActive,
	className,
}: {
	users: UsageUser[];
	range: UsageRange;
	// Client-side email search — narrows this table only, no server call.
	emailQuery: string;
	// True when a server-side feature/model filter is active; tokens/cost/
	// turns then reflect the slice while budget columns stay unfiltered.
	filterActive: boolean;
	className?: string;
}) {
	const [sortKey, setSortKey] = useState<SortKey>("cost_usd");
	const [sortDir, setSortDir] = useState<1 | -1>(-1);

	const shown = useMemo(() => {
		const q = emailQuery.trim().toLowerCase();
		return q ? users.filter((u) => u.email.toLowerCase().includes(q)) : users;
	}, [users, emailQuery]);

	const sorted = useMemo(() => {
		const val = (u: UsageUser): string | number => {
			switch (sortKey) {
				case "email":
					return u.email.toLowerCase();
				case "tier":
					return tierTag(u).label;
				case "budget":
					// Exempt/unbudgeted users sink below 0% on a descending sort.
					return u.budget_used_pct ?? -1;
				case "status":
					return STATUS_ORDER[u.status];
				case "last_active":
					return u.last_active ?? "";
				default:
					return u[sortKey];
			}
		};
		return [...shown].sort((a, b) => {
			const ka = val(a);
			const kb = val(b);
			const c =
				typeof ka === "string" ? ka.localeCompare(String(kb)) : ka - Number(kb);
			return c * sortDir;
		});
	}, [shown, sortKey, sortDir]);

	const onSort = (c: (typeof COLS)[number]) => {
		if (c.key === sortKey) {
			setSortDir((d) => (d === 1 ? -1 : 1));
		} else {
			setSortKey(c.key);
			// Numbers (and budget %/recency) read best big-first; text A→Z.
			setSortDir(c.key === "email" || c.key === "tier" ? 1 : -1);
		}
	};

	const totPrompt = shown.reduce((s, u) => s + u.prompt_tokens, 0);
	const totCompletion = shown.reduce((s, u) => s + u.completion_tokens, 0);
	const totCost = shown.reduce((s, u) => s + u.cost_usd, 0);

	return (
		<Panel
			title={`Usage by user — ${range} days`}
			action={
				<span className="font-mono text-[11px] text-[var(--cds-helper)]">
					click a column to sort
				</span>
			}
			className={className}
		>
			<div className="overflow-x-auto">
				<table className="w-full min-w-[960px] border-collapse text-left">
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
									{emailQuery.trim()
										? "No users match that email."
										: "No usage in this period."}
								</td>
							</tr>
						) : (
							sorted.map((u) => {
								const tier = tierTag(u);
								const status = STATUS_TAGS[u.status];
								return (
									<tr
										key={u.id}
										className="border-[var(--cds-border)] border-b transition-colors hover:bg-[var(--cds-layer)]"
									>
										<td className="whitespace-nowrap px-3 py-2.5">
											<p className="text-[13px]">{u.email}</p>
											{u.name && (
												<p className="text-[var(--cds-helper)] text-xs">
													{u.name}
												</p>
											)}
										</td>
										<td className="whitespace-nowrap px-3 py-2.5">
											<Tag kind={tier.kind}>{tier.label}</Tag>
										</td>
										<td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[13px] tabular-nums">
											{fmtInt(u.turns)}
										</td>
										<td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[13px] tabular-nums">
											{fmtTok(u.prompt_tokens)}
										</td>
										<td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[13px] tabular-nums">
											{fmtTok(u.completion_tokens)}
										</td>
										<td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[13px] tabular-nums">
											{fmtMoney(u.cost_usd)}
										</td>
										<td className="whitespace-nowrap px-3 py-2.5">
											<BudgetMeter user={u} />
										</td>
										<td className="whitespace-nowrap px-3 py-2.5">
											<Tag kind={status.kind}>{status.label}</Tag>
										</td>
										<td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[13px] text-[var(--cds-text-2)] tabular-nums">
											{u.last_active ? fmtDay(u.last_active) : "—"}
										</td>
									</tr>
								);
							})
						)}
					</tbody>
					<tfoot>
						<tr>
							<td
								colSpan={COLS.length}
								className="border-[var(--cds-border-strong)] border-t px-3 py-2.5 text-[var(--cds-helper)] text-xs"
							>
								{fmtInt(shown.length)} users · totals: {fmtTok(totPrompt)}{" "}
								prompt / {fmtTok(totCompletion)} completion ·{" "}
								{fmtMoney(totCost)} spend · budgets are month-to-date
								{filterActive && " (budget columns ignore filters)"}
							</td>
						</tr>
					</tfoot>
				</table>
			</div>
		</Panel>
	);
}

function BudgetMeter({ user }: { user: UsageUser }) {
	const pct = user.budget_used_pct;
	if (pct === null || user.status === "exempt") {
		return (
			<span className="font-mono text-[var(--cds-helper)] text-xs">—</span>
		);
	}
	const fill =
		user.status === "capped"
			? "#da1e28"
			: user.status === "near"
				? "#f1c21b"
				: BLUE;
	return (
		<span className="inline-flex items-center gap-2">
			<span className="h-1.5 w-16 bg-[var(--cds-layer-selected)]">
				<span
					className="block h-full"
					style={{
						width: `${Math.min(100, Math.max(0, pct))}%`,
						background: fill,
					}}
				/>
			</span>
			<span className="w-10 text-right font-mono text-[var(--cds-text-2)] text-xs tabular-nums">
				{Math.round(pct)}%
			</span>
		</span>
	);
}
