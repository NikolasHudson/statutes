"use client";

// Iowa business entity search.
//
// The URL is the single source of truth — every field writes to the query
// string and the effect re-runs from it — so a search is a link a colleague
// can open, and the back button walks the searches you actually ran.
//
// Names are matched on a normalized form (punctuation and entity suffix
// dropped, see backend apps/resources/normalize.py): "wood doctor" finds
// "\" THE WOOD DOCTOR, L. C. \"". A pure-digit query is a corp-number lookup
// and pins the exact row first.

import { SearchIcon } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import {
	BtnGhost,
	BtnPrimary,
	CheckboxRow,
	Notification,
	PageHead,
	Panel,
	SelectField,
	TextField,
} from "@/components/carbon/primitives";
import {
	EntityTable,
	ProvenanceStrip,
} from "@/components/resources/provenance";
import {
	type EntitySearchResponse,
	type EntityTypeCount,
	entityTypes,
	ResourcesError,
	searchEntities,
} from "@/lib/iowa-resources";

const PAGE_SIZE = 25;

type FormState = {
	q: string;
	agent: string;
	city: string;
	zip: string;
	type: string;
	includeInactive: boolean;
};

const EMPTY: FormState = {
	q: "",
	agent: "",
	city: "",
	zip: "",
	type: "",
	includeInactive: false,
};

function formFromParams(sp: URLSearchParams): FormState {
	return {
		q: sp.get("q") ?? "",
		agent: sp.get("agent") ?? "",
		city: sp.get("city") ?? "",
		zip: sp.get("zip") ?? "",
		type: sp.get("type") ?? "",
		includeInactive: sp.get("include_inactive") === "true",
	};
}

function paramsFromForm(form: FormState, page: number): string {
	const sp = new URLSearchParams();
	if (form.q.trim()) sp.set("q", form.q.trim());
	if (form.agent.trim()) sp.set("agent", form.agent.trim());
	if (form.city.trim()) sp.set("city", form.city.trim());
	if (form.zip.trim()) sp.set("zip", form.zip.trim());
	if (form.type) sp.set("type", form.type);
	if (form.includeInactive) sp.set("include_inactive", "true");
	if (page > 1) sp.set("page", String(page));
	return sp.toString();
}

function hasFilter(form: FormState): boolean {
	return Boolean(
		form.q.trim() || form.agent.trim() || form.city.trim() || form.zip.trim(),
	);
}

export default function BusinessEntitySearchPage() {
	return (
		<Suspense
			fallback={
				<div className="px-5 py-10 text-[var(--cds-text-2)] text-sm sm:px-8">
					Loading…
				</div>
			}
		>
			<SearchScreen />
		</Suspense>
	);
}

function SearchScreen() {
	const router = useRouter();
	const searchParams = useSearchParams();
	const spStr = searchParams.toString();

	const urlForm = useMemo(
		() => formFromParams(new URLSearchParams(spStr)),
		[spStr],
	);
	const page = Math.max(1, Number(searchParams.get("page")) || 1);

	// The form is local state seeded from the URL, so typing does not push a
	// history entry per keystroke; submitting is what writes the URL.
	const [form, setForm] = useState<FormState>(urlForm);
	useEffect(() => setForm(urlForm), [urlForm]);

	const [data, setData] = useState<EntitySearchResponse | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<Error | null>(null);
	const [types, setTypes] = useState<EntityTypeCount[]>([]);

	useEffect(() => {
		const controller = new AbortController();
		entityTypes(controller.signal)
			.then((d) => setTypes(d.types))
			// The filter is a convenience; a failure here must not break search.
			.catch(() => undefined);
		return () => controller.abort();
	}, []);

	useEffect(() => {
		const sp = new URLSearchParams(spStr);
		const active = formFromParams(sp);
		if (!hasFilter(active)) {
			setData(null);
			setError(null);
			return;
		}
		const controller = new AbortController();
		setLoading(true);
		setError(null);
		searchEntities(
			{
				q: active.q,
				agent: active.agent,
				city: active.city,
				zip: active.zip,
				type: active.type,
				include_inactive: active.includeInactive,
				page: Math.max(1, Number(sp.get("page")) || 1),
				page_size: PAGE_SIZE,
			},
			controller.signal,
		)
			.then(setData)
			.catch((e) => {
				if (controller.signal.aborted) return;
				setError(e as Error);
				setData(null);
			})
			.finally(() => {
				if (!controller.signal.aborted) setLoading(false);
			});
		return () => controller.abort();
	}, [spStr]);

	const go = (next: FormState, nextPage = 1) => {
		const query = paramsFromForm(next, nextPage);
		router.push(
			query
				? `/resources/iowa-business-entities?${query}`
				: "/resources/iowa-business-entities",
		);
	};

	const typeOptions = useMemo(
		() => [
			{ value: "", label: "Any entity type" },
			...types.map((t) => ({
				value: t.type,
				label: `${t.type} (${t.count.toLocaleString("en-US")})`,
			})),
		],
		[types],
	);

	const totalLabel = data
		? `${data.total.toLocaleString("en-US")}${data.total_capped ? "+" : ""}`
		: "";
	const lastPage = data
		? Math.max(1, Math.ceil(data.total / (data.page_size || PAGE_SIZE)))
		: 1;

	return (
		<div className="px-5 py-10 sm:px-8 lg:py-14">
			<PageHead
				eyebrow="Reference data"
				title="Iowa business entities"
				lede="Every entity on the Secretary of State's active list: legal name, type, effective date, registered agent and principal office. Search by name, corporation number, registered agent, city or ZIP."
			/>

			<form
				className="mt-10 max-w-4xl"
				onSubmit={(e) => {
					e.preventDefault();
					go(form);
				}}
			>
				<TextField
					label="Name or corporation number"
					placeholder="e.g. wood doctor, or 662502"
					value={form.q}
					onChange={(e) => setForm({ ...form, q: e.target.value })}
					helper="Punctuation and entity form are ignored — “L. C.”, “LC” and “LLC” all match."
				/>

				<div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
					<TextField
						label="Registered agent"
						value={form.agent}
						onChange={(e) => setForm({ ...form, agent: e.target.value })}
					/>
					<TextField
						label="City"
						value={form.city}
						onChange={(e) => setForm({ ...form, city: e.target.value })}
					/>
					<TextField
						label="ZIP"
						inputMode="numeric"
						value={form.zip}
						onChange={(e) => setForm({ ...form, zip: e.target.value })}
					/>
					<SelectField
						label="Entity type"
						options={typeOptions}
						value={form.type}
						onChange={(e) => setForm({ ...form, type: e.target.value })}
					/>
				</div>

				<div className="mt-5">
					<CheckboxRow
						label="Include entities no longer listed as active"
						detail="The source publishes active filings only; these are entities we have seen drop off it."
						checked={form.includeInactive}
						onChange={(v) => setForm({ ...form, includeInactive: v })}
					/>
				</div>

				<div className="mt-7 flex flex-wrap items-center gap-3">
					<BtnPrimary type="submit" disabled={!hasFilter(form)}>
						<span className="inline-flex items-center gap-2">
							<SearchIcon className="size-4" />
							Search
						</span>
					</BtnPrimary>
					<BtnGhost
						type="button"
						onClick={() => {
							setForm(EMPTY);
							router.push("/resources/iowa-business-entities");
						}}
					>
						Clear
					</BtnGhost>
				</div>
			</form>

			{!hasFilter(urlForm) && (
				<p className="mt-10 max-w-2xl text-[var(--cds-text-2)] text-sm">
					Enter a name, corporation number, registered agent, city or ZIP to
					search. There is no full listing: this registry names private
					individuals at their home addresses, so it answers questions rather
					than handing over the file.
				</p>
			)}

			{error && (
				<Notification
					className="mt-8 max-w-2xl"
					kind={
						error instanceof ResourcesError &&
						(error.status === 402 || error.status === 429)
							? "warning"
							: "error"
					}
					title={
						error instanceof ResourcesError
							? error.status === 402
								? "Resources needs an active plan"
								: error.status === 429
									? "Too many searches"
									: "Search failed"
							: "Search failed"
					}
				>
					{error.message}
				</Notification>
			)}

			{loading && (
				<p className="mt-8 text-[var(--cds-text-2)] text-sm">Searching…</p>
			)}

			{data && !loading && (
				<section className="mt-10">
					<Panel
						title={`${totalLabel} ${data.total === 1 ? "match" : "matches"}`}
						action={
							lastPage > 1 ? (
								<span className="font-mono text-[11px] text-[var(--cds-helper)]">
									Page {data.page} of {lastPage}
								</span>
							) : undefined
						}
					>
						<EntityTable
							rows={data.results}
							emptyLabel={
								page > 1
									? "No more results on this page."
									: "No entities matched. Try fewer filters, or check the spelling."
							}
						/>
					</Panel>

					{lastPage > 1 && (
						<div className="mt-4 flex items-center gap-3">
							<BtnGhost
								type="button"
								disabled={page <= 1}
								onClick={() => go(urlForm, page - 1)}
							>
								Previous
							</BtnGhost>
							<BtnGhost
								type="button"
								disabled={page >= lastPage}
								onClick={() => go(urlForm, page + 1)}
							>
								Next
							</BtnGhost>
						</div>
					)}

					{data.total_capped && (
						<p className="mt-4 text-[var(--cds-helper)] text-xs">
							Showing the first {data.total.toLocaleString("en-US")} matches.
							Add a city, ZIP or entity type to narrow the search.
						</p>
					)}

					<div className="mt-8 max-w-3xl">
						<ProvenanceStrip asOf={data.as_of} />
					</div>
				</section>
			)}
		</div>
	);
}
