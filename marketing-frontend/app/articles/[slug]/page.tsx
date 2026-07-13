// Article reader for the Hudson Legal Technologies marketing site
// (/articles/[slug]). Content is DB-backed: markdown files in
// backend/content/articles/ are imported by `manage.py import_articles`, and
// articles can equally be authored in the Django admin — either way this
// template fetches from /api/marketing/articles/{slug} with ISR, so new or
// edited posts appear without a redeploy.
//
// Carbon register: dark #161616 article header (+ optional bespoke lead
// figure, see article-leads.tsx), hairline rules instead of cards, mono
// eyebrows, square everything. Prose is hand-styled via article-body.tsx.

import { ArrowLeftIcon } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArticleBody } from "@/components/marketing/article-body";
import { articleLead } from "@/components/marketing/article-leads";
import {
	CarbonPage,
	Eyebrow,
	INK,
	SolidLink,
	TextLink,
} from "@/components/marketing/carbon";
import { ARTICLES_HREF } from "@/components/marketing/chrome";
import { ShareButtons } from "@/components/marketing/share-buttons";
import {
	type ArticleCard,
	type ArticleDetail,
	fetchArticle,
	fetchArticles,
	fetchArticlesStrict,
	formatArticleDate,
} from "@/lib/api";
import { APP_URL } from "@/lib/site";
import { cn } from "@/lib/utils";

type Params = { slug: string };

// Strict: this decides which article pages exist in the build at all. A
// backend blip during `next build` would otherwise prerender none of them —
// green build, no articles, and every link from the index and the sitemap
// resolving through a cold runtime fetch or not at all.
export async function generateStaticParams(): Promise<Params[]> {
	return (await fetchArticlesStrict()).map((a) => ({ slug: a.slug }));
}

export async function generateMetadata({
	params,
}: {
	params: Promise<Params>;
}): Promise<Metadata> {
	const article = await fetchArticle((await params).slug);
	if (!article) return { title: "Article — Hudson Legal Technologies" };
	return {
		title: `${article.title} — Hudson Legal Technologies`,
		description: article.lede || article.excerpt,
	};
}

export default async function ArticlePage({
	params,
}: {
	params: Promise<Params>;
}) {
	const { slug } = await params;
	const article = await fetchArticle(slug);
	if (!article) notFound();

	const related = (await fetchArticles())
		.filter((a) => a.slug !== slug)
		.slice(0, 3);
	const lead = articleLead(slug);

	return (
		<CarbonPage>
			<ArticleHeader article={article} />
			{lead && (
				<section className={cn("text-white", INK)}>
					<div className="mx-auto max-w-7xl px-5 pb-16 sm:px-8">{lead}</div>
				</section>
			)}

			{/* Reading layout: the article column starts at the same left gutter as
			    the header and matches the title's max-w-5xl (64rem) measure exactly;
			    the share rail takes the leftover right-hand space. */}
			<div className="mx-auto grid max-w-7xl gap-10 px-5 pb-8 sm:px-8 lg:grid-cols-[minmax(0,64rem)_1fr]">
				<article className="w-full">
					<ArticleBody markdown={article.body_md} />
					{article.tags.length > 0 && <TagRow tags={article.tags} />}
					<InlineCta />
				</article>
				<ShareRail title={article.title} />
			</div>

			<AuthorBio article={article} />
			<KeepReading related={related} />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Header — dark leadspace, Plex-light title, blue accent rule
// ---------------------------------------------------------------------------

function ArticleHeader({ article }: { article: ArticleDetail }) {
	return (
		<header className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 pt-12 pb-14 sm:px-8 lg:pt-16">
				<Link
					href={ARTICLES_HREF}
					className="inline-flex items-center gap-1.5 text-[#c6c6c6] text-sm transition-colors hover:text-white"
				>
					<ArrowLeftIcon className="size-4" />
					All articles
				</Link>

				<div className="mt-8">
					<Eyebrow tone="dark">
						{article.category} · Insights ·{" "}
						{formatArticleDate(article.published_at)}
					</Eyebrow>
				</div>

				<h1 className="mt-6 max-w-5xl font-light text-3xl leading-[1.15] sm:text-[2.6rem] lg:text-[3.25rem]">
					{article.title}
				</h1>

				<div aria-hidden className="mt-8 h-0.5 w-24 bg-[#0f62fe]" />

				{article.lede && (
					<p className="mt-8 max-w-3xl text-[#c6c6c6] text-lg leading-relaxed">
						{article.lede}
					</p>
				)}

				<div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 text-[#c6c6c6] text-sm">
					<span className="font-medium text-white">{article.author_name}</span>
					<span>{article.author_title}</span>
					<span aria-hidden className="hidden h-4 w-px bg-[#393939] sm:block" />
					<span>{article.read_minutes} min read</span>
				</div>
			</div>
		</header>
	);
}

// ---------------------------------------------------------------------------
// Tags + share + inline CTA
// ---------------------------------------------------------------------------

function TagRow({ tags }: { tags: string[] }) {
	return (
		<p className="mt-12 border-border border-t pt-8 font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
			{tags.join(" · ")}
		</p>
	);
}

function InlineCta() {
	return (
		<div className="mt-10 flex flex-col gap-5 border-border border-y py-8 sm:flex-row sm:items-center sm:justify-between">
			<div>
				<h3 className="font-semibold text-lg">
					See grounded answers for yourself
				</h3>
				<p className="mt-1 text-[14px] text-muted-foreground">
					In beta now. Ask a question, follow the citation to the source.
				</p>
			</div>
			<div className="shrink-0">
				<SolidLink href={APP_URL}>Try Hudson</SolidLink>
			</div>
		</div>
	);
}

// Right rail — sticky share controls, squared with a muted gray hover.
function ShareRail({ title }: { title: string }) {
	return (
		<aside className="hidden lg:block">
			<div className="sticky top-24 flex flex-col gap-2">
				<p className="font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
					Share
				</p>
				<ShareButtons title={title} />
			</div>
		</aside>
	);
}

// ---------------------------------------------------------------------------
// Author bio — hairline-ruled block, square monogram
// ---------------------------------------------------------------------------

function AuthorBio({ article }: { article: ArticleDetail }) {
	const monogram = article.author_name
		.split(/\s+/)
		.map((w) => w[0])
		.join("")
		.slice(0, 2)
		.toUpperCase();
	return (
		<section className="border-border border-y bg-card">
			<div className="mx-auto max-w-7xl px-5 py-12 sm:px-8">
				<div className="flex max-w-5xl flex-col gap-5 sm:flex-row">
					<span className="flex size-14 shrink-0 items-center justify-center bg-[#161616] font-mono text-sm text-white">
						{monogram}
					</span>
					<div>
						<Eyebrow>Written by</Eyebrow>
						<h3 className="mt-2 font-semibold text-lg">
							{article.author_name}
						</h3>
						<p className="mt-2 text-[15px] text-muted-foreground leading-relaxed">
							{article.author_title}. Writing about retrieval, verification, and
							what it takes to trust AI with the law.
						</p>
					</div>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Keep reading — hairline tiles, same register as the index. Only rendered
// once there is more than one published article.
// ---------------------------------------------------------------------------

function KeepReading({ related }: { related: ArticleCard[] }) {
	if (related.length === 0) return null;
	return (
		<section className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-20">
			<div className="flex flex-wrap items-end justify-between gap-4 border-border border-t pt-6">
				<div>
					<Eyebrow>Articles</Eyebrow>
					<h2 className="mt-6 font-light text-3xl">Keep reading</h2>
				</div>
				<TextLink href={ARTICLES_HREF}>All articles</TextLink>
			</div>

			<div className="mt-10 grid divide-y divide-border border border-border md:grid-cols-3 md:divide-x md:divide-y-0">
				{related.map((r) => (
					<Link
						key={r.slug}
						href={`/articles/${r.slug}`}
						className="group flex min-h-[200px] flex-col bg-card p-8 transition-colors hover:bg-[#e8e8e8]"
					>
						<Eyebrow>{r.category}</Eyebrow>
						<h3 className="mt-4 flex-1 text-xl leading-snug">{r.title}</h3>
						<span className="mt-6 flex items-center justify-between font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
							{r.read_minutes} min read
							<span
								aria-hidden
								className="text-[#0f62fe] transition-transform group-hover:translate-x-0.5"
							>
								→
							</span>
						</span>
					</Link>
				))}
			</div>
		</section>
	);
}
