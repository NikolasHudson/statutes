// Article-reader mockup for the Hudson Legal Tech marketing site.
//
// A single long-form post under the marketing tree (/home-mockup/articles/...),
// rendered with the shared site chrome. Server component so it can carry real
// <metadata>; the only interactive piece (the nav) is a client component
// imported from chrome. Prose is hand-styled (the app doesn't ship the
// typography plugin) to keep full control of the reading rhythm.

import {
	ArrowLeftIcon,
	ArrowRightIcon,
	CheckIcon,
	ClockIcon,
	LinkIcon,
	type LucideIcon,
	NewspaperIcon,
	ScaleIcon,
	Share2Icon,
	ShieldCheckIcon,
	XIcon,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import {
	ARTICLE_HREF,
	MARKETING_HOME,
	navyBackdrop,
	SiteFooter,
	SiteNav,
} from "@/components/marketing/chrome";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
	title: "Why Legal AI Keeps Inventing Citations — Hudson Legal Tech",
	description:
		"Fluent text and trustworthy text are not the same thing. The difference between an AI that sounds right and one you can actually cite.",
};

const ARTICLES_INDEX = `${MARKETING_HOME}#more`;

export default function ArticlePage() {
	return (
		<div className="min-h-dvh bg-background text-foreground">
			<SiteNav />
			<ArticleHeader />
			<LeadFigure />

			<div className="mx-auto grid max-w-6xl gap-10 px-5 pb-8 sm:px-8 lg:grid-cols-[1fr_minmax(0,680px)_1fr]">
				<div className="hidden lg:block" aria-hidden />
				<article className="w-full max-w-[680px]">
					<Body />
					<TagRow />
					<InlineCta />
				</article>
				<ShareRail />
			</div>

			<AuthorBio />
			<KeepReading />
			<SiteFooter />
		</div>
	);
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

function ArticleHeader() {
	return (
		<header className="border-border border-b bg-card">
			<div className="mx-auto max-w-3xl px-5 py-12 sm:px-8 lg:py-16">
				<Link
					href={ARTICLES_INDEX}
					className="inline-flex items-center gap-1.5 font-medium text-muted-foreground text-sm transition-colors hover:text-foreground"
				>
					<ArrowLeftIcon className="size-4" />
					All articles
				</Link>

				<div className="mt-6 flex items-center gap-2">
					<span className="rounded-full bg-primary/10 px-2.5 py-1 font-semibold text-[11px] text-primary uppercase tracking-[0.12em]">
						Grounding
					</span>
					<span className="text-[13px] text-muted-foreground">Insights</span>
				</div>

				<h1 className="mt-4 font-bold text-3xl leading-[1.12] tracking-tight sm:text-[2.6rem]">
					Why Legal AI Keeps Inventing Citations — and What Grounding Actually
					Fixes
				</h1>

				<p className="mt-5 text-lg text-muted-foreground leading-relaxed">
					Fluent text and trustworthy text are not the same thing. Here's the
					difference between an AI that sounds right and one you can hand to a
					court.
				</p>

				<div className="mt-8 flex flex-wrap items-center gap-4">
					<div className="flex items-center gap-3">
						<span className="flex size-10 items-center justify-center rounded-full bg-primary font-semibold text-primary-foreground text-sm">
							NH
						</span>
						<div className="leading-tight">
							<div className="font-semibold text-sm">Nick Hudson</div>
							<div className="text-[13px] text-muted-foreground">
								Founder, Hudson Legal Tech
							</div>
						</div>
					</div>
					<span className="hidden h-8 w-px bg-border sm:block" />
					<div className="flex items-center gap-4 text-[13px] text-muted-foreground">
						<span>June 24, 2026</span>
						<span className="inline-flex items-center gap-1.5">
							<ClockIcon className="size-3.5" />8 min read
						</span>
					</div>
				</div>
			</div>
		</header>
	);
}

// On-brand lead visual: the article's thesis in one glance — an invented
// citation struck down next to a verified one.
function LeadFigure() {
	return (
		<figure className="mx-auto max-w-4xl px-5 pt-10 sm:px-8 lg:pt-14">
			<div
				className="relative overflow-hidden rounded-2xl border border-white/10 p-8 text-white shadow-sm sm:p-12"
				style={navyBackdrop}
			>
				<p className="font-semibold text-[12px] text-white/60 uppercase tracking-[0.16em]">
					The same question, two kinds of answer
				</p>
				<div className="mt-6 space-y-3">
					<div className="flex items-center gap-3 rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-3">
						<span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-red-500/90 text-white">
							<XIcon className="size-3.5" strokeWidth={3} />
						</span>
						<span className="text-[14px] text-white/90 line-through decoration-red-300/70">
							Smith v. Jefferson County, 482 N.W.2d 119 (Iowa 1994)
						</span>
						<span className="ms-auto hidden shrink-0 font-medium text-[12px] text-red-200 sm:block">
							Not in any reporter
						</span>
					</div>
					<div className="flex items-center gap-3 rounded-xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-3">
						<span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-white">
							<CheckIcon className="size-3.5" strokeWidth={3} />
						</span>
						<span className="text-[14px] text-white/90">
							Iowa Code § 714H.5 (2023)
						</span>
						<span className="ms-auto hidden shrink-0 font-medium text-[12px] text-emerald-200 sm:block">
							Verified against source
						</span>
					</div>
				</div>
			</div>
			<figcaption className="mt-3 text-center text-[13px] text-muted-foreground">
				A confident-looking citation and a real one are indistinguishable until
				something checks them.
			</figcaption>
		</figure>
	);
}

// ---------------------------------------------------------------------------
// Body — hand-styled prose
// ---------------------------------------------------------------------------

function Body() {
	return (
		<div className="pt-10 lg:pt-14">
			<P className="first-letter:float-left first-letter:mr-2 first-letter:font-bold first-letter:text-6xl first-letter:text-primary first-letter:leading-[0.8]">
				In June 2023, two New York lawyers were sanctioned for submitting a
				brief full of cases that did not exist. They hadn't made them up — a
				chatbot had. It produced citations, parallel reporters, even fabricated
				internal quotations, all formatted perfectly. The lawyers filed it. The
				cases were fiction.
			</P>
			<P>
				That episode gets told as a story about careless lawyers. It's really a
				story about how generative AI works — and why most legal AI tools, even
				today, are built to make the same mistake look more convincing.
			</P>

			<H2 id="the-problem">A $5,000 lesson in fluency</H2>
			<P>
				The model wasn't broken. It did exactly what it was designed to do:
				produce the most plausible-sounding continuation of the prompt. A
				citation is a highly patterned object — a case name, a volume, a
				reporter, a page, a year. A system trained on millions of them can
				generate a flawless-looking one without any case behind it. Fluency was
				never the problem. Fluency was the trap.
			</P>

			<H2 id="fluency">Fluency is not grounding</H2>
			<P>
				A large language model is, at heart, a next-token predictor. Ask it a
				question and it doesn't look anything up — it writes the words most
				likely to follow your question, given everything it absorbed in
				training. For prose, that's remarkable. For law, it's dangerous, because
				the part you most need to trust — the citation — is exactly the part the
				model is most willing to invent.
			</P>
			<P>
				This is why "we use GPT-4" tells you almost nothing about whether a
				legal tool is safe. The base model is the same one that fabricated those
				cases. What matters is everything wrapped around it.
			</P>

			<H2 id="grounding">What grounding actually means</H2>
			<P>
				Grounding flips the order of operations. Instead of asking the model to
				answer from memory, you first retrieve the actual authoritative text —
				the statute, the rule, the decision — and hand it to the model as the
				only material it's allowed to reason from. The model's job stops being
				"recall the law" and becomes "summarize and explain <em>this</em> text,
				and cite it."
			</P>
			<P>
				At Hudson, that material is a maintained corpus of the Iowa Code, Court
				Rules, and caselaw — the currently effective, human-reviewed text, with
				its citation, effective date, and enacting session law attached.
				Retrieval is hybrid: full-text and trigram matching for precision,
				vector embeddings for the semantically-phrased question, fused together
				so the on-point provision surfaces whether you typed its number or
				described what it does.
			</P>

			<Pullquote>
				A citation you have to double-check isn't a citation. It's a lead.
			</Pullquote>

			<H2 id="verification">The step most tools skip</H2>
			<P>
				Here's the uncomfortable part: grounding alone is necessary but not
				sufficient. Give a model the right passage and it can still paraphrase a
				quote slightly wrong, attribute it to the neighboring section, or carry
				over a citation from context that doesn't actually support the sentence
				it's attached to. Retrieval reduces hallucination. It doesn't eliminate
				it.
			</P>
			<P>
				So Hudson adds a step that runs <em>after</em> the model writes its
				answer and <em>before</em> you ever see it: a deterministic check that
				walks every citation and every quoted span and confirms it against the
				source text. A quote that isn't verbatim, or a citation that points at
				text that doesn't support the claim, gets caught — not by another model
				asked to grade itself, but by code comparing strings to the corpus.
			</P>
			<Callout
				icon={ShieldCheckIcon}
				title="Why deterministic, not another model?"
			>
				Asking a second LLM "is this right?" inherits the same failure mode you
				were trying to escape. A string-and-citation check against the source is
				boring, fast, and — crucially — can't be charmed by a confident-sounding
				answer.
			</Callout>

			<H2 id="in-practice">What it looks like in practice</H2>
			<P>
				Ask Hudson whether Iowa recognizes a private right of action under its
				Consumer Fraud Act, and you get a direct answer anchored to{" "}
				<Cite>Iowa Code § 714H.5</Cite> — with the citation linked to the
				official text, the effective date shown, and a small badge confirming
				every citation in the answer was verified against the source.
			</P>
			<P>
				The more important behavior is the one you don't see advertised: when
				the corpus doesn't actually support an answer, Hudson tells you that,
				instead of producing a plausible-looking case to fill the gap. "I can't
				find support for that" is, in legal research, a feature.
			</P>

			<H2 id="bottom-line">The bottom line</H2>
			<P>
				The lawyers in that 2023 case weren't undone by a bad model. They were
				undone by a tool that optimized for sounding right over being right —
				and gave them no way to tell the difference. Grounding, real citations,
				and verification aren't features you bolt on for marketing. They're the
				difference between a draft you have to re-check line by line and an
				answer you can put your name on.
			</P>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Prose primitives
// ---------------------------------------------------------------------------

function P({
	children,
	className = "",
}: {
	children: React.ReactNode;
	className?: string;
}) {
	return (
		<p
			className={`mt-5 text-[17px] text-foreground/85 leading-[1.75] ${className}`}
		>
			{children}
		</p>
	);
}

function H2({ id, children }: { id: string; children: React.ReactNode }) {
	return (
		<h2
			id={id}
			className="mt-12 scroll-mt-24 font-bold text-2xl tracking-tight"
		>
			{children}
		</h2>
	);
}

function Pullquote({ children }: { children: React.ReactNode }) {
	return (
		<blockquote className="my-10 border-primary border-l-4 pl-6">
			<p className="font-medium text-foreground text-xl italic leading-relaxed">
				{children}
			</p>
		</blockquote>
	);
}

function Callout({
	icon: Icon,
	title,
	children,
}: {
	icon: LucideIcon;
	title: string;
	children: React.ReactNode;
}) {
	return (
		<div className="my-8 rounded-xl border border-border bg-secondary/50 p-5">
			<div className="flex items-center gap-2.5">
				<span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
					<Icon className="size-4.5" />
				</span>
				<p className="font-semibold text-[15px]">{title}</p>
			</div>
			<p className="mt-3 text-[15px] text-muted-foreground leading-relaxed">
				{children}
			</p>
		</div>
	);
}

function Cite({ children }: { children: React.ReactNode }) {
	return (
		<span className="mx-0.5 inline-flex items-center gap-1 rounded border border-primary/20 bg-primary/10 px-1.5 py-px font-medium text-[14px] text-primary">
			<ScaleIcon className="size-3.5" />
			{children}
		</span>
	);
}

// ---------------------------------------------------------------------------
// Tags + share + inline CTA
// ---------------------------------------------------------------------------

const TAGS = ["Grounding", "Hallucination", "Citations", "RAG", "Legal AI"];

function TagRow() {
	return (
		<div className="mt-12 flex flex-wrap gap-2 border-border border-t pt-8">
			{TAGS.map((t) => (
				<span
					key={t}
					className="rounded-full bg-secondary px-3 py-1 font-medium text-[12px] text-muted-foreground"
				>
					{t}
				</span>
			))}
		</div>
	);
}

function InlineCta() {
	return (
		<div className="mt-10 overflow-hidden rounded-2xl border border-border bg-card">
			<div className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
				<div>
					<h3 className="font-semibold text-lg tracking-tight">
						See grounded answers for yourself
					</h3>
					<p className="mt-1 text-[14px] text-muted-foreground">
						Free during beta. Ask a question, follow the citation to the source.
					</p>
				</div>
				<Button asChild size="lg" className="shrink-0">
					<Link href="/">
						Try Hudson
						<ArrowRightIcon />
					</Link>
				</Button>
			</div>
		</div>
	);
}

// Right rail — sticky share controls.
function ShareRail() {
	const buttons: { icon: LucideIcon; label: string }[] = [
		{ icon: LinkIcon, label: "Copy link" },
		{ icon: Share2Icon, label: "Share" },
	];
	return (
		<aside className="hidden lg:block">
			<div className="sticky top-24 flex flex-col gap-2">
				<p className="font-semibold text-[12px] text-muted-foreground uppercase tracking-[0.14em]">
					Share
				</p>
				{buttons.map((b) => {
					const Icon = b.icon;
					return (
						<button
							key={b.label}
							type="button"
							className="flex size-9 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary"
							aria-label={b.label}
						>
							<Icon className="size-4" />
						</button>
					);
				})}
			</div>
		</aside>
	);
}

// ---------------------------------------------------------------------------
// Author bio
// ---------------------------------------------------------------------------

function AuthorBio() {
	return (
		<section className="border-border border-y bg-card">
			<div className="mx-auto max-w-3xl px-5 py-12 sm:px-8">
				<div className="flex flex-col gap-5 sm:flex-row">
					<span className="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary font-semibold text-lg text-primary-foreground">
						NH
					</span>
					<div>
						<p className="font-semibold text-[12px] text-primary uppercase tracking-[0.14em]">
							Written by
						</p>
						<h3 className="mt-1 font-semibold text-lg tracking-tight">
							Nick Hudson
						</h3>
						<p className="mt-2 text-[15px] text-muted-foreground leading-relaxed">
							Founder of Hudson Legal Tech, building grounded, citable AI
							research tools for practitioners. Writing about retrieval,
							verification, and what it takes to trust AI with the law.
						</p>
					</div>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Keep reading
// ---------------------------------------------------------------------------

type Related = { category: string; title: string; read: string };

const RELATED: Related[] = [
	{
		category: "Search",
		title: "Reciprocal Rank Fusion, explained for lawyers",
		read: "6 min read",
	},
	{
		category: "Currency",
		title: 'What "currently in force" really means in a statute',
		read: "5 min read",
	},
	{
		category: "Engineering",
		title: "Connecting Hudson to Claude Desktop over MCP",
		read: "7 min read",
	},
];

function KeepReading() {
	return (
		<section className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
			<div className="flex items-end justify-between gap-4">
				<h2 className="font-bold text-2xl tracking-tight">Keep reading</h2>
				<Link
					href={ARTICLES_INDEX}
					className="inline-flex items-center gap-1.5 font-medium text-primary text-sm hover:underline"
				>
					All articles
					<ArrowRightIcon className="size-4" />
				</Link>
			</div>

			<div className="mt-8 grid gap-6 md:grid-cols-3">
				{RELATED.map((r) => (
					<Link
						key={r.title}
						href={ARTICLE_HREF}
						className="group flex flex-col rounded-2xl border border-border bg-card p-6 transition-shadow hover:shadow-md"
					>
						<div className="flex items-center gap-2 text-muted-foreground">
							<NewspaperIcon className="size-4" />
							<span className="font-semibold text-[11px] text-primary uppercase tracking-[0.12em]">
								{r.category}
							</span>
						</div>
						<h3 className="mt-3 flex-1 font-semibold text-lg leading-snug tracking-tight transition-colors group-hover:text-primary">
							{r.title}
						</h3>
						<div className="mt-4 flex items-center gap-1.5 text-[13px] text-muted-foreground">
							<ClockIcon className="size-3.5" />
							{r.read}
						</div>
					</Link>
				))}
			</div>
		</section>
	);
}
