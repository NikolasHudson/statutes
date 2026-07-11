"use client";

// Shared article editor for /admin/articles/new (create) and
// /admin/articles/[id] (edit). Content column carries title + a markdown
// body with an Edit/Preview line-tab pair; the rail carries publish state
// and metadata. The preview is a readable approximation — the marketing
// site's own /articles/[slug] template is the real rendering (drop cap,
// pullquotes, callouts), and published edits show there within five minutes.

import { useRouter } from "next/navigation";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
	BtnDanger,
	BtnGhost,
	BtnPrimary,
	FieldLabel,
	LineTabs,
	Notification,
	Panel,
	TextAreaField,
	TextField,
	ToggleRow,
} from "@/components/carbon/primitives";
import {
	type AdminArticleDetail,
	type AdminArticleIn,
	createAdminArticle,
	deleteAdminArticle,
	patchAdminArticle,
} from "@/lib/iowa-admin";

// The marketing site is a separate deployment; without its origin configured
// the "view on site" link has nowhere to point, so it hides.
const MARKETING_URL = process.env.NEXT_PUBLIC_MARKETING_URL ?? "";

// Matches the backend's derivation (django slugify, ascii-ish) closely
// enough for the live hint; the server has the final say.
function slugify(title: string): string {
	return title
		.toLowerCase()
		.normalize("NFKD")
		.replace(/[̀-ͯ]/g, "")
		.replace(/[^a-z0-9\s-]/g, "")
		.trim()
		.replace(/[\s-]+/g, "-");
}

function todayISO(): string {
	const d = new Date();
	const p = (n: number) => String(n).padStart(2, "0");
	return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function ArticleEditor({
	initial,
}: {
	initial?: AdminArticleDetail; // absent = create mode
}) {
	const router = useRouter();
	const creating = !initial;

	const [title, setTitle] = useState(initial?.title ?? "");
	const [slug, setSlug] = useState(initial?.slug ?? "");
	const [slugTouched, setSlugTouched] = useState(!creating);
	const [category, setCategory] = useState(initial?.category ?? "");
	const [lede, setLede] = useState(initial?.lede ?? "");
	const [excerpt, setExcerpt] = useState(initial?.excerpt ?? "");
	const [body, setBody] = useState(initial?.body_md ?? "");
	const [tags, setTags] = useState((initial?.tags ?? []).join(", "));
	const [authorName, setAuthorName] = useState(initial?.author_name ?? "");
	const [authorTitle, setAuthorTitle] = useState(initial?.author_title ?? "");
	const [published, setPublished] = useState(initial?.published ?? false);
	const [publishedAt, setPublishedAt] = useState(initial?.published_at ?? "");
	const [readMinutes, setReadMinutes] = useState(
		initial ? String(initial.read_minutes) : "0",
	);

	const [tab, setTab] = useState<"edit" | "preview">("edit");
	const [saving, setSaving] = useState(false);
	const [saved, setSaved] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [confirmDelete, setConfirmDelete] = useState(false);

	const effectiveSlug = slugTouched ? slug : slugify(title);

	const payload = (): AdminArticleIn => ({
		title: title.trim(),
		slug: effectiveSlug.trim(),
		category: category.trim(),
		lede: lede.trim(),
		excerpt: excerpt.trim(),
		body_md: body,
		tags: tags
			.split(",")
			.map((t) => t.trim())
			.filter(Boolean),
		author_name: authorName.trim(),
		author_title: authorTitle.trim(),
		published,
		published_at: publishedAt || null,
		read_minutes: Math.max(0, Number(readMinutes) || 0),
	});

	async function save() {
		setSaving(true);
		setError(null);
		setSaved(false);
		try {
			if (creating) {
				const created = await createAdminArticle(payload());
				router.replace(`/admin/articles/${created.id}`);
			} else {
				const updated = await patchAdminArticle(initial.id, payload());
				setReadMinutes(String(updated.read_minutes));
				setSlug(updated.slug);
				setSaved(true);
			}
		} catch (e) {
			setError((e as Error).message);
		} finally {
			setSaving(false);
		}
	}

	async function remove() {
		if (!initial) return;
		setSaving(true);
		setError(null);
		try {
			await deleteAdminArticle(initial.id);
			router.replace("/admin/articles");
		} catch (e) {
			setError((e as Error).message);
			setSaving(false);
			setConfirmDelete(false);
		}
	}

	return (
		<div className="mt-8">
			{initial?.source_path && (
				<Notification
					kind="warning"
					title="Synced from a markdown file"
					className="mb-6 max-w-2xl"
				>
					This article comes from {initial.source_path}. You can edit it here
					and changes go live, but the next import_articles run will overwrite
					them from the file — put permanent edits in the file itself.
				</Notification>
			)}
			{error && (
				<Notification
					kind="error"
					title="Couldn't save"
					className="mb-6 max-w-2xl"
				>
					{error}
				</Notification>
			)}
			{saved && (
				<Notification kind="success" title="Saved" className="mb-6 max-w-2xl">
					{published
						? "Live on the marketing site within five minutes."
						: "Saved as a draft — not visible on the site."}
				</Notification>
			)}

			<div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
				{/* Content column */}
				<div className="min-w-0">
					<TextField
						label="Title"
						value={title}
						onChange={(e) => setTitle(e.target.value)}
						placeholder="Why Legal AI Keeps Inventing Citations…"
					/>
					<TextAreaField
						label="Lede"
						helper="Opens the article header on the site — one or two sentences."
						className="mt-5"
						rows={2}
						value={lede}
						onChange={(e) => setLede(e.target.value)}
					/>
					<TextAreaField
						label="Excerpt"
						helper="Sells the article on the index cards."
						className="mt-5"
						rows={3}
						value={excerpt}
						onChange={(e) => setExcerpt(e.target.value)}
					/>

					<div className="mt-8">
						<LineTabs
							tabs={[
								{ id: "edit" as const, label: "Body (markdown)" },
								{ id: "preview" as const, label: "Preview" },
							]}
							value={tab}
							onChange={setTab}
						/>
						{tab === "edit" ? (
							<TextAreaField
								helper="GitHub-flavored markdown. A blockquote renders as a pullquote; a blockquote whose first line is **bold** renders as a callout box."
								className="mt-4"
								rows={26}
								value={body}
								onChange={(e) => setBody(e.target.value)}
								spellCheck
								style={{ fontFamily: "var(--font-mono, monospace)" }}
							/>
						) : (
							<div className="mt-4 min-h-64 border border-[var(--cds-border)] bg-[var(--cds-layer)] px-6 py-5">
								{body.trim() ? (
									<div className="max-w-2xl [&_a]:text-[var(--cds-link)] [&_a]:underline [&_blockquote]:my-6 [&_blockquote]:border-[#0f62fe] [&_blockquote]:border-l-2 [&_blockquote]:pl-5 [&_code]:font-mono [&_code]:text-[13px] [&_h2]:mt-8 [&_h2]:font-semibold [&_h2]:text-xl [&_h3]:mt-6 [&_h3]:font-semibold [&_h3]:text-lg [&_li]:mt-1 [&_ol]:mt-4 [&_ol]:list-decimal [&_ol]:pl-6 [&_p]:mt-4 [&_p]:text-[15px] [&_p]:leading-relaxed [&_ul]:mt-4 [&_ul]:list-disc [&_ul]:pl-6">
										<ReactMarkdown remarkPlugins={[remarkGfm]}>
											{body}
										</ReactMarkdown>
									</div>
								) : (
									<p className="text-[var(--cds-helper)] text-sm">
										Nothing to preview yet.
									</p>
								)}
							</div>
						)}
					</div>
				</div>

				{/* Metadata rail */}
				<div className="space-y-6">
					<Panel title="Publish">
						<div className="px-4 pb-4">
							<ToggleRow
								label="Published"
								detail={
									published
										? "Visible on the marketing site."
										: "Draft — hidden from the site."
								}
								on={published}
								onChange={(v) => {
									setPublished(v);
									if (v && !publishedAt) setPublishedAt(todayISO());
								}}
							/>
							<TextField
								label="Publication date"
								type="date"
								value={publishedAt}
								onChange={(e) => setPublishedAt(e.target.value)}
							/>
							<div className="mt-6 flex flex-col gap-2">
								<BtnPrimary
									size="md"
									arrow={false}
									className="justify-center"
									disabled={saving || !title.trim()}
									onClick={() => void save()}
								>
									{saving
										? "Saving…"
										: creating
											? "Create article"
											: "Save changes"}
								</BtnPrimary>
								{!creating && initial.published && MARKETING_URL && (
									<a
										href={`${MARKETING_URL}/articles/${initial.slug}`}
										className="text-center text-[var(--cds-link)] text-xs hover:underline"
										target="_blank"
										rel="noreferrer"
									>
										View on marketing site ↗
									</a>
								)}
							</div>
						</div>
					</Panel>

					<Panel title="Metadata">
						<div className="space-y-5 px-4 pb-5">
							<TextField
								label="Slug"
								helper={
									creating && !slugTouched
										? "Derived from the title — edit to override."
										: "Changing this changes the article's URL."
								}
								value={effectiveSlug}
								onChange={(e) => {
									setSlugTouched(true);
									setSlug(e.target.value);
								}}
							/>
							<TextField
								label="Category"
								helper="Eyebrow on cards — e.g. Grounding, Search, Engineering."
								value={category}
								onChange={(e) => setCategory(e.target.value)}
							/>
							<TextField
								label="Tags"
								helper="Comma-separated."
								value={tags}
								onChange={(e) => setTags(e.target.value)}
							/>
							<TextField
								label="Read minutes"
								helper="0 = compute from word count on save."
								type="number"
								min={0}
								value={readMinutes}
								onChange={(e) => setReadMinutes(e.target.value)}
							/>
							<TextField
								label="Author"
								placeholder="Nick Hudson"
								value={authorName}
								onChange={(e) => setAuthorName(e.target.value)}
							/>
							<TextField
								label="Author title"
								placeholder="Founder, Hudson Legal Technologies"
								value={authorTitle}
								onChange={(e) => setAuthorTitle(e.target.value)}
							/>
						</div>
					</Panel>

					{!creating && !initial.source_path && (
						<Panel title="Danger zone">
							<div className="px-4 pb-4">
								<FieldLabel>
									Deleting removes the article from the site immediately.
								</FieldLabel>
								{confirmDelete ? (
									<div className="mt-2 flex gap-2">
										<BtnDanger
											size="md"
											disabled={saving}
											onClick={() => void remove()}
										>
											Confirm delete
										</BtnDanger>
										<BtnGhost size="md" onClick={() => setConfirmDelete(false)}>
											Cancel
										</BtnGhost>
									</div>
								) : (
									<BtnDanger
										size="md"
										className="mt-2"
										onClick={() => setConfirmDelete(true)}
									>
										Delete article
									</BtnDanger>
								)}
							</div>
						</Panel>
					)}
				</div>
			</div>
		</div>
	);
}
