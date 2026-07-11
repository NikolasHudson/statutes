"use client";

// Admin · Articles — staff-only management of the marketing site's articles
// over /api/admin/articles. Lists every article including drafts (the public
// site only serves published ones); rows synced from repo markdown files get
// an "md file" tag because import_articles overwrites admin edits to them.
// Creating and editing happens on /admin/articles/new and /admin/articles/[id].

import Link from "next/link";
import { useEffect, useState } from "react";
import {
	BtnGhost,
	BtnPrimary,
	Eyebrow,
	Notification,
	Panel,
	Tag,
} from "@/components/carbon/primitives";
import { AccountError } from "@/lib/iowa-account";
import { type AdminArticleRow, getAdminArticles } from "@/lib/iowa-admin";

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

function fmtDate(iso: string | null): string {
	const m = iso && /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
	if (!m) return "—";
	return `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}`;
}

const HEADERS = [
	"Article",
	"Category",
	"Status",
	"Published",
	"Read",
	"Source",
];

export default function AdminArticlesPage() {
	const [rows, setRows] = useState<AdminArticleRow[] | null>(null);
	const [error, setError] = useState<Error | null>(null);

	useEffect(() => {
		let cancelled = false;
		getAdminArticles()
			.then((r) => !cancelled && setRows(r))
			.catch((e) => !cancelled && setError(e as Error));
		return () => {
			cancelled = true;
		};
	}, []);

	const httpStatus = error instanceof AccountError ? error.status : null;

	return (
		<div className="mx-auto w-full max-w-[1320px] px-5 py-10 sm:px-8">
			<header className="flex flex-wrap items-end justify-between gap-6">
				<div>
					<Eyebrow>Admin · Marketing site</Eyebrow>
					<h1 className="mt-4 font-light text-3xl sm:text-4xl">Articles</h1>
					<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
						Everything the marketing site's /articles section serves, drafts
						included. Published changes go live within five minutes — no deploy.
					</p>
				</div>
				<Link href="/admin/articles/new">
					<BtnPrimary size="md">New article</BtnPrimary>
				</Link>
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
			) : error ? (
				<Notification
					kind="error"
					title="Couldn't load articles"
					className="mt-10 max-w-xl"
				>
					{error.message}
				</Notification>
			) : rows === null ? (
				<p className="mt-10 text-[var(--cds-text-2)] text-sm">
					Loading articles…
				</p>
			) : (
				<div className="mt-8">
					<Panel
						title={`All articles — ${rows.length} ${rows.length === 1 ? "entry" : "entries"}`}
					>
						<div className="overflow-x-auto">
							<table className="w-full min-w-[760px] border-collapse text-left">
								<thead>
									<tr>
										{HEADERS.map((h) => (
											<th
												key={h}
												className="whitespace-nowrap border-[var(--cds-border-strong)] border-b bg-[var(--cds-layer)] px-3 py-2.5 font-mono font-normal text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.1em]"
											>
												{h}
											</th>
										))}
									</tr>
								</thead>
								<tbody>
									{rows.length === 0 ? (
										<tr>
											<td
												colSpan={HEADERS.length}
												className="px-3 py-6 text-center text-[var(--cds-text-2)] text-sm"
											>
												No articles yet — write the first one.
											</td>
										</tr>
									) : (
										rows.map((a) => (
											<tr
												key={a.id}
												className="border-[var(--cds-border)] border-b transition-colors hover:bg-[var(--cds-layer)]"
											>
												<td className="max-w-md px-3 py-2.5">
													<Link
														href={`/admin/articles/${a.id}`}
														className="group block"
													>
														<p className="truncate text-[13px] text-[var(--cds-link)] group-hover:underline">
															{a.title}
														</p>
														<p className="truncate font-mono text-[var(--cds-helper)] text-xs">
															/articles/{a.slug}
														</p>
													</Link>
												</td>
												<td className="whitespace-nowrap px-3 py-2.5 text-[13px] text-[var(--cds-text-2)]">
													{a.category || "—"}
												</td>
												<td className="whitespace-nowrap px-3 py-2.5">
													{a.published ? (
														<Tag kind="green">Published</Tag>
													) : (
														<Tag kind="gray">Draft</Tag>
													)}
												</td>
												<td className="whitespace-nowrap px-3 py-2.5 font-mono text-[13px] text-[var(--cds-text-2)] tabular-nums">
													{fmtDate(a.published_at)}
												</td>
												<td className="whitespace-nowrap px-3 py-2.5 font-mono text-[13px] text-[var(--cds-text-2)] tabular-nums">
													{a.read_minutes} min
												</td>
												<td className="whitespace-nowrap px-3 py-2.5">
													{a.source_path ? (
														<Tag kind="purple">md file</Tag>
													) : (
														<Tag kind="blue">admin</Tag>
													)}
												</td>
											</tr>
										))
									)}
								</tbody>
							</table>
						</div>
					</Panel>
					<p className="mt-4 text-[var(--cds-helper)] text-xs">
						"md file" rows are synced from backend/content/articles/ — edits
						here survive until the next import_articles run; edit the file for
						permanent changes.
					</p>
				</div>
			)}
		</div>
	);
}
