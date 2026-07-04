// Article-reader mockup for the Hudson Legal Technologies marketing site.
//
// A single long-form post under the marketing tree (/articles/...), rendered
// in the Carbon register: dark #161616 article header + lead figure, hairline
// rules instead of cards, mono eyebrows, square everything. Server component
// so it can carry real <metadata>; interactive chrome comes from CarbonPage.
// Prose is hand-styled (the app doesn't ship the typography plugin) to keep
// full control of the reading rhythm.

import {
	ArrowLeftIcon,
	CheckIcon,
	LinkIcon,
	type LucideIcon,
	ScaleIcon,
	Share2Icon,
	ShieldCheckIcon,
	XIcon,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import {
	CarbonPage,
	Eyebrow,
	INK,
	SolidLink,
	TextLink,
} from "@/components/marketing/carbon";
import { ARTICLE_HREF, ARTICLES_HREF } from "@/components/marketing/chrome";
import { APP_URL } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title: "Why Legal AI Keeps Inventing Citations — Hudson Legal Technologies",
	description:
		"Fluent text and trustworthy text are not the same thing. The difference between an AI that sounds right and one you can actually cite.",
};

const ARTICLES_INDEX = ARTICLES_HREF;

export default function ArticlePage() {
	return (
		<CarbonPage>
			<ArticleHeader />
			<LeadFigure />

			{/* Reading layout: the article column starts at the same left gutter as
			    the header and matches the title's max-w-5xl (64rem) measure exactly;
			    the share rail takes the leftover right-hand space. */}
			<div className="mx-auto grid max-w-7xl gap-10 px-5 pb-8 sm:px-8 lg:grid-cols-[minmax(0,64rem)_1fr]">
				<article className="w-full">
					<Body />
					<TagRow />
					<InlineCta />
				</article>
				<ShareRail />
			</div>

			<AuthorBio />
			<KeepReading />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Header — dark leadspace, Plex-light title, blue accent rule
// ---------------------------------------------------------------------------

function ArticleHeader() {
	return (
		<header className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 pt-12 pb-14 sm:px-8 lg:pt-16">
				<Link
					href={ARTICLES_INDEX}
					className="inline-flex items-center gap-1.5 text-[#c6c6c6] text-sm transition-colors hover:text-white"
				>
					<ArrowLeftIcon className="size-4" />
					All articles
				</Link>

				<div className="mt-8">
					<Eyebrow tone="dark">Grounding · Insights · June 24, 2026</Eyebrow>
				</div>

				<h1 className="mt-6 max-w-5xl font-light text-3xl leading-[1.15] sm:text-[2.6rem] lg:text-[3.25rem]">
					Why Legal AI Keeps Inventing Citations — and What Grounding Actually
					Fixes
				</h1>

				<div aria-hidden className="mt-8 h-0.5 w-24 bg-[#0f62fe]" />

				<p className="mt-8 max-w-3xl text-[#c6c6c6] text-lg leading-relaxed">
					Fluent text and trustworthy text are not the same thing. Here's the
					difference between an AI that sounds right and one you can hand to a
					court.
				</p>

				<div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 text-[#c6c6c6] text-sm">
					<span className="font-medium text-white">Nick Hudson</span>
					<span>Founder, Hudson Legal Technologies</span>
					<span aria-hidden className="hidden h-4 w-px bg-[#393939] sm:block" />
					<span>8 min read</span>
				</div>
			</div>
		</header>
	);
}

// On-brand lead visual: the article's thesis in one glance — an invented
// citation struck down next to a verified one. Flat on gray-100, hairline
// #393939 borders, Blue-60/Blue-40 accents; continues the header band.
function LeadFigure() {
	return (
		<section className={cn("text-white", INK)}>
			{/* Aligned with the header title and article column: same 7xl gutter,
			    same max-w-5xl (64rem) cap. */}
			<div className="mx-auto max-w-7xl px-5 pb-16 sm:px-8">
				<figure className="max-w-5xl">
					<div className="border border-[#393939] p-6 sm:p-8">
						<p className="font-mono text-[#a8a8a8] text-[11px] uppercase tracking-[0.22em]">
							The same question, two kinds of answer
						</p>
						<div className="mt-6 space-y-3">
							<div className="flex items-center gap-3 border border-[#393939] px-4 py-3">
								<span className="flex size-6 shrink-0 items-center justify-center border border-[#6f6f6f] text-[#a8a8a8]">
									<XIcon className="size-3.5" strokeWidth={2.5} />
								</span>
								<span className="text-[#a8a8a8] text-[14px] line-through decoration-[#6f6f6f]">
									Smith v. Jefferson County, 482 N.W.2d 119 (Iowa 1994)
								</span>
								<span className="ms-auto hidden shrink-0 font-mono text-[#a8a8a8] text-[11px] uppercase tracking-[0.16em] sm:block">
									Not in any reporter
								</span>
							</div>
							<div className="flex items-center gap-3 border border-[#393939] px-4 py-3">
								<span className="flex size-6 shrink-0 items-center justify-center bg-[#0f62fe] text-white">
									<CheckIcon className="size-3.5" strokeWidth={2.5} />
								</span>
								<span className="text-[14px] text-white">
									Iowa Code § 714H.5 (2023)
								</span>
								<span className="ms-auto hidden shrink-0 font-mono text-[#78a9ff] text-[11px] uppercase tracking-[0.16em] sm:block">
									Verified against source
								</span>
							</div>
						</div>
					</div>
					<figcaption className="mt-4 text-[#a8a8a8] text-[13px]">
						A confident-looking citation and a real one are indistinguishable
						until something checks them.
					</figcaption>
				</figure>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Body — hand-styled prose
// ---------------------------------------------------------------------------

function Body() {
	return (
		<div className="pt-10 lg:pt-14">
			<P className="first-letter:float-left first-letter:mr-2 first-letter:font-light first-letter:text-6xl first-letter:text-[#0f62fe] first-letter:leading-[0.8]">
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
		<h2 id={id} className="mt-12 scroll-mt-24 font-semibold text-2xl">
			{children}
		</h2>
	);
}

function Pullquote({ children }: { children: React.ReactNode }) {
	return (
		<blockquote className="my-10 border-[#0f62fe] border-l-2 pl-6">
			<p className="font-light text-2xl text-foreground leading-snug">
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
		<div className="my-8 border border-border border-l-2 border-l-[#0f62fe] bg-card p-5">
			<div className="flex items-center gap-2.5">
				<Icon className="size-5 text-[#0f62fe]" />
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
		<span className="mx-0.5 inline-flex items-center gap-1 border border-border bg-card px-1.5 py-px font-medium text-[#0f62fe] text-[14px]">
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
		<p className="mt-12 border-border border-t pt-8 font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
			{TAGS.join(" · ")}
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
function ShareRail() {
	const buttons: { icon: LucideIcon; label: string }[] = [
		{ icon: LinkIcon, label: "Copy link" },
		{ icon: Share2Icon, label: "Share" },
	];
	return (
		<aside className="hidden lg:block">
			<div className="sticky top-24 flex flex-col gap-2">
				<p className="font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
					Share
				</p>
				{buttons.map((b) => {
					const Icon = b.icon;
					return (
						<button
							key={b.label}
							type="button"
							className="flex size-9 items-center justify-center border border-border bg-card text-muted-foreground transition-colors hover:bg-[#e8e8e8] hover:text-foreground"
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
// Author bio — hairline-ruled block, square monogram
// ---------------------------------------------------------------------------

function AuthorBio() {
	return (
		<section className="border-border border-y bg-card">
			<div className="mx-auto max-w-7xl px-5 py-12 sm:px-8">
				<div className="flex max-w-5xl flex-col gap-5 sm:flex-row">
					<span className="flex size-14 shrink-0 items-center justify-center bg-[#161616] font-mono text-sm text-white">
						NH
					</span>
					<div>
						<Eyebrow>Written by</Eyebrow>
						<h3 className="mt-2 font-semibold text-lg">Nick Hudson</h3>
						<p className="mt-2 text-[15px] text-muted-foreground leading-relaxed">
							Founder of Hudson Legal Technologies, building grounded, citable
							AI research tools for practitioners. Writing about retrieval,
							verification, and what it takes to trust AI with the law.
						</p>
					</div>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Keep reading — hairline tiles, same register as the index
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
		<section className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-20">
			<div className="flex flex-wrap items-end justify-between gap-4 border-border border-t pt-6">
				<div>
					<Eyebrow>Articles</Eyebrow>
					<h2 className="mt-6 font-light text-3xl">Keep reading</h2>
				</div>
				<TextLink href={ARTICLES_INDEX}>All articles</TextLink>
			</div>

			<div className="mt-10 grid divide-y divide-border border border-border md:grid-cols-3 md:divide-x md:divide-y-0">
				{RELATED.map((r) => (
					<Link
						key={r.title}
						href={ARTICLE_HREF}
						className="group flex min-h-[200px] flex-col bg-card p-8 transition-colors hover:bg-[#e8e8e8]"
					>
						<Eyebrow>{r.category}</Eyebrow>
						<h3 className="mt-4 flex-1 text-xl leading-snug">{r.title}</h3>
						<span className="mt-6 flex items-center justify-between font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
							{r.read}
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
