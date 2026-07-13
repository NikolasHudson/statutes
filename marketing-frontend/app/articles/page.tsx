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

// An "In the works" list of four unwritten articles — with invented read times —
// used to sit here. It was fiction dressed as a publishing schedule. Articles
// appear on this page when they are written and published, and not before.
//
// A hardcoded FALLBACK card used to sit here too, mirroring the first imported
// article so the index was "never empty". It pointed at
// /articles/why-legal-ai-invents-citations — which does not exist on prod
// (`/api/marketing/articles` → 200 `[]`), so the featured slot on the live site
// would have been a link straight to a 404. A dead featured article on launch
// day is worse than no article, and an empty index is not a failure: it is a
// site that has not published yet. Say so plainly instead.

export default async function ArticlesIndexPage() {
	const articles = await fetchArticles();
	const [featured, ...rest] = articles;

	return (
		<CarbonPage>
			<PageHero
				eyebrow="Articles & Insights"
				title="Field notes on legal AI."
				lede="Practical writing on grounding, retrieval, and verification — what it actually takes to trust AI with a citation, from the team building it."
			/>
			{featured ? <FeaturedLead article={featured} /> : <NothingYet />}
			{rest.length > 0 && <ArticleList articles={rest} />}
			<Subscribe n={rest.length > 0 ? "03" : "02"} />
		</CarbonPage>
	);
}

// Empty state — shown when nothing is published yet (or the backend is
// unreachable at render time). Carries no link: there is nowhere honest to send
// anyone. The newsletter band below is the call to action.
function NothingYet() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<header className="border-border border-t pt-6">
					<Eyebrow>01 — Latest article</Eyebrow>
				</header>

				<div className="mt-12 border border-border bg-card p-8 sm:p-10">
					<h2 className="max-w-3xl font-light text-3xl leading-[1.15] sm:text-4xl">
						Nothing published yet.
					</h2>
					<p className="mt-5 max-w-2xl text-lg text-muted-foreground leading-relaxed">
						We're writing. The first pieces — on grounding, retrieval, and what
						citation verification actually buys you — are on the way. Subscribe
						below and they'll land in your inbox as they go up.
					</p>
				</div>
			</div>
		</section>
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
