// Articles index for the Hudson Legal Technologies marketing site (/articles).
//
// Carbon register — dark leadspace, numbered sections over hairline rules,
// square tiles instead of cards, mono eyebrows, dark newsletter band. Server
// component (carries <metadata>); nav and subscribe form are client pieces.

import type { Metadata } from "next";
import Link from "next/link";
import {
	CarbonPage,
	Eyebrow,
	INK,
	PageHero,
	SectionHead,
} from "@/components/marketing/carbon";
import { ARTICLE_HREF } from "@/components/marketing/chrome";
import { SubscribeForm } from "@/components/marketing/subscribe-form";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title: "Articles & Insights — Hudson Legal Technologies",
	description:
		"Practical writing on grounding, retrieval, verification, and what it takes to trust AI with the law — from the team building Hudson.",
};

type Article = {
	href?: string;
	category: string;
	title: string;
	excerpt: string;
	date?: string;
	read: string;
	status?: "published" | "soon";
};

const FEATURED: Article = {
	href: ARTICLE_HREF,
	category: "Grounding",
	title:
		"Why Legal AI Keeps Inventing Citations — and What Grounding Actually Fixes",
	excerpt:
		"Fluent text and trustworthy text are not the same thing. The difference between an AI that sounds right and one you can hand to a court — and why most legal AI tools make the same mistake look more convincing.",
	date: "June 24, 2026",
	read: "8 min read",
	status: "published",
};

const UPCOMING: Article[] = [
	{
		category: "Search",
		title: "Reciprocal Rank Fusion, explained for lawyers",
		excerpt:
			"Why keyword search and semantic search each miss things — and how fusing them surfaces the on-point provision either way.",
		read: "6 min read",
		status: "soon",
	},
	{
		category: "Currency",
		title: 'What "currently in force" really means in a statute',
		excerpt:
			"Effective dates, amendments, and supersession — the difference between the law today and the law that used to be.",
		read: "5 min read",
		status: "soon",
	},
	{
		category: "Engineering",
		title: "Connecting Hudson to Claude Desktop over MCP",
		excerpt:
			"A walkthrough of wiring a grounded legal corpus into your own tools over a production MCP endpoint.",
		read: "7 min read",
		status: "soon",
	},
	{
		category: "Verification",
		title: "Why we check citations with code, not another model",
		excerpt:
			"Asking a second LLM to grade the first inherits the same failure mode. What a deterministic check buys you.",
		read: "5 min read",
		status: "soon",
	},
];

export default function ArticlesIndexPage() {
	return (
		<CarbonPage>
			<PageHero
				eyebrow="Articles & Insights"
				title="Field notes on legal AI."
				lede="Practical writing on grounding, retrieval, and verification — what it actually takes to trust AI with a citation, from the team building it."
			/>
			<FeaturedLead article={FEATURED} />
			<UpcomingList articles={UPCOMING} />
			<Subscribe />
		</CarbonPage>
	);
}

// Featured lead — a single hairline tile carrying the full editorial weight.
function FeaturedLead({ article }: { article: Article }) {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<header className="border-border border-t pt-6">
					<Eyebrow>01 — Latest article</Eyebrow>
				</header>

				<Link
					href={article.href ?? "#"}
					className="group mt-12 block border border-border bg-card p-8 transition-colors hover:bg-[#e8e8e8] sm:p-10"
				>
					<Eyebrow>
						{article.category} · {article.date} · {article.read}
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

// Upcoming — muted, non-interactive hairline tiles; mono "Coming soon" label.
function UpcomingList({ articles }: { articles: Article[] }) {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 pb-20 sm:px-8 lg:pb-28">
				<SectionHead n="02" label="In the works" title="More on the way." />

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
function Subscribe() {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<SectionHead
					n="03"
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
