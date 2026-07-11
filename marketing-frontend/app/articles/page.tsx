// Articles index for the Hudson Legal Technologies marketing site (/articles).
//
// Published articles come from the backend (/api/marketing/articles — markdown
// files imported by `manage.py import_articles`, or posts authored in the
// Django admin) with ISR, so new posts appear without a redeploy. A static
// fallback card keeps the page whole if the backend is unreachable at render
// time. Carbon register — dark leadspace, numbered sections over hairline
// rules, square tiles instead of cards, mono eyebrows, dark newsletter band.

import type { Metadata } from "next";
import Link from "next/link";
import {
	CarbonPage,
	Eyebrow,
	INK,
	PageHero,
	SectionHead,
} from "@/components/marketing/carbon";
import { SubscribeForm } from "@/components/marketing/subscribe-form";
import { type ArticleCard, fetchArticles, formatArticleDate } from "@/lib/api";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title: "Articles & Insights — Hudson Legal Technologies",
	description:
		"Practical writing on grounding, retrieval, verification, and what it takes to trust AI with the law — from the team building Hudson.",
};

// Fallback if the backend can't be reached when the page renders — mirrors
// the first imported article so the index is never empty.
const FALLBACK: ArticleCard[] = [
	{
		slug: "why-legal-ai-invents-citations",
		category: "Grounding",
		title:
			"Why Legal AI Keeps Inventing Citations — and What Grounding Actually Fixes",
		excerpt:
			"Fluent text and trustworthy text are not the same thing. The difference between an AI that sounds right and one you can hand to a court — and why most legal AI tools make the same mistake look more convincing.",
		published_at: "2026-06-24",
		read_minutes: 8,
	},
];

type Upcoming = {
	category: string;
	title: string;
	excerpt: string;
	read: string;
};

const UPCOMING: Upcoming[] = [
	{
		category: "Search",
		title: "Reciprocal Rank Fusion, explained for lawyers",
		excerpt:
			"Why keyword search and semantic search each miss things — and how fusing them surfaces the on-point provision either way.",
		read: "6 min read",
	},
	{
		category: "Currency",
		title: 'What "currently in force" really means in a statute',
		excerpt:
			"Effective dates, amendments, and supersession — the difference between the law today and the law that used to be.",
		read: "5 min read",
	},
	{
		category: "Engineering",
		title: "Connecting Hudson to Claude Desktop over MCP",
		excerpt:
			"A walkthrough of wiring a grounded legal corpus into your own tools over a production MCP endpoint.",
		read: "7 min read",
	},
	{
		category: "Verification",
		title: "Why we check citations with code, not another model",
		excerpt:
			"Asking a second LLM to grade the first inherits the same failure mode. What a deterministic check buys you.",
		read: "5 min read",
	},
];

export default async function ArticlesIndexPage() {
	const fetched = await fetchArticles();
	const articles = fetched.length > 0 ? fetched : FALLBACK;
	const [featured, ...rest] = articles;
	// A teaser graduates off the "in the works" list the day it's published.
	const publishedTitles = new Set(articles.map((a) => a.title.toLowerCase()));
	const upcoming = UPCOMING.filter(
		(u) => !publishedTitles.has(u.title.toLowerCase()),
	);

	return (
		<CarbonPage>
			<PageHero
				eyebrow="Articles & Insights"
				title="Field notes on legal AI."
				lede="Practical writing on grounding, retrieval, and verification — what it actually takes to trust AI with a citation, from the team building it."
			/>
			<FeaturedLead article={featured} />
			{rest.length > 0 && <ArticleList articles={rest} />}
			{upcoming.length > 0 && (
				<UpcomingList articles={upcoming} n={rest.length > 0 ? "03" : "02"} />
			)}
			<Subscribe n={rest.length > 0 ? "04" : "03"} />
		</CarbonPage>
	);
}

// Featured lead — a single hairline tile carrying the full editorial weight.
function FeaturedLead({ article }: { article: ArticleCard }) {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<header className="border-border border-t pt-6">
					<Eyebrow>01 — Latest article</Eyebrow>
				</header>

				<Link
					href={`/articles/${article.slug}`}
					className="group mt-12 block border border-border bg-card p-8 transition-colors hover:bg-[#e8e8e8] sm:p-10"
				>
					<Eyebrow>
						{article.category} · {formatArticleDate(article.published_at)} ·{" "}
						{article.read_minutes} min read
					</Eyebrow>
					<h2 className="mt-6 max-w-4xl font-light text-3xl leading-[1.15] sm:text-4xl lg:text-[2.75rem]">
						{article.title}
					</h2>
					<p className="mt-5 max-w-2xl text-lg text-muted-foreground leading-relaxed">
						{article.excerpt}
					</p>
					<span className="mt-8 inline-flex items-center gap-2 font-medium text-[#0f62fe] text-sm group-hover:underline">
						Read article
						<span
							aria-hidden
							className="transition-transform group-hover:translate-x-0.5"
						>
							→
						</span>
					</span>
				</Link>
			</div>
		</section>
	);
}

// Every published article after the featured one — clickable hairline rows.
function ArticleList({ articles }: { articles: ArticleCard[] }) {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 pb-20 sm:px-8 lg:pb-28">
				<SectionHead n="02" label="All articles" title="More from the field." />

				<div className="mt-14 grid divide-y divide-border border border-border">
					{articles.map((a) => (
						<Link
							key={a.slug}
							href={`/articles/${a.slug}`}
							className="group grid gap-x-10 gap-y-3 bg-card p-8 transition-colors hover:bg-[#e8e8e8] sm:grid-cols-[9rem_1fr_auto]"
						>
							<Eyebrow>{a.category}</Eyebrow>
							<div>
								<h3 className="max-w-xl text-foreground text-xl leading-snug group-hover:underline">
									{a.title}
								</h3>
								<p className="mt-2 max-w-xl text-[14px] text-muted-foreground leading-relaxed">
									{a.excerpt}
								</p>
							</div>
							<p className="font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em] sm:text-right">
								{formatArticleDate(a.published_at)} · {a.read_minutes} min read
							</p>
						</Link>
					))}
				</div>
			</div>
		</section>
	);
}

// Upcoming — muted, non-interactive hairline tiles; mono "Coming soon" label.
function UpcomingList({ articles, n }: { articles: Upcoming[]; n: string }) {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 pb-20 sm:px-8 lg:pb-28">
				<SectionHead n={n} label="In the works" title="More on the way." />

				<div className="mt-14 grid divide-y divide-border border border-border">
					{articles.map((a) => (
						<div
							key={a.title}
							className="grid gap-x-10 gap-y-3 bg-card p-8 sm:grid-cols-[9rem_1fr_auto]"
						>
							<Eyebrow>{a.category}</Eyebrow>
							<div>
								<h3 className="max-w-xl font-light text-foreground/80 text-xl leading-snug">
									{a.title}
								</h3>
								<p className="mt-2 max-w-xl text-[14px] text-muted-foreground leading-relaxed">
									{a.excerpt}
								</p>
							</div>
							<p className="font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em] sm:text-right">
								Coming soon · {a.read}
							</p>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

// Subscribe — dark band, consistent with the Carbon home's ink sections.
function Subscribe({ n }: { n: string }) {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<SectionHead
					n={n}
					label="Newsletter"
					title="Get new articles by email."
					tone="dark"
				/>
				<p className="mt-6 max-w-md text-[#c6c6c6] leading-relaxed">
					Occasional, substantive, no spam. Unsubscribe anytime.
				</p>
				<div className="mt-8">
					<SubscribeForm tone="dark" />
				</div>
			</div>
		</section>
	);
}
