// Pricing page for the Hudson Legal Technologies marketing site (/pricing),
// in the Carbon (IBM design system) register — dark leadspace, hairline tier
// tiles, ruled FAQ rows, ink CTA band. Chrome + primitives come from
// components/marketing/carbon.tsx.
//
// Launch pricing per PRICING_STRATEGY.md (2026-07-11): Solo $49/mo ($490/yr),
// Firm $149/mo incl. 3 seats +$39/seat, Enterprise custom. Every paid plan
// starts with a 7-day card-up-front trial — there is no free tier. Honest
// framing: while billing is dark (NEXT_PUBLIC_BILLING_LIVE unset) the page says
// plainly that these are announced launch prices and beta users get notice
// before any charge. Server component (carries <metadata>).

import { CheckIcon } from "lucide-react";
import type { Metadata } from "next";
import {
	CarbonPage,
	Eyebrow,
	HairlineLink,
	INK,
	PageHero,
	SectionHead,
	SolidLink,
} from "@/components/marketing/carbon";
import { CONSULTING_HREF } from "@/components/marketing/chrome";
import {
	type CorpusStats,
	corpusSourceProse,
	fetchCorpusStats,
} from "@/lib/api";
import { BILLING_LIVE, PLANS, type Plan, type PlanKey } from "@/lib/pricing";
import { APP_URL, BRAND_NAME } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title: "Pricing — Hudson Legal Technologies",
	description:
		"Solo $49/month, Firm $149/month including 3 seats. Every plan starts with a 7-day free trial — no surprise charges.",
};

// Name, price, cadence, tagline and CTA come from lib/pricing.ts — the same
// literals the product pages' Pricing band renders, so the two surfaces cannot
// quote different prices. What stays here is what only this page shows: the
// per-tier feature lists, which are derived from the live corpus.
type Tier = Plan & {
	features: string[];
	featured?: boolean;
};

// The tier list is a function of the LIVE corpus, not a hand-typed literal.
//
// The Solo bullet used to read "Full search — Iowa Code, admin code, Acts &
// caselaw". Prod serves `iowa-acts` with entries: 0 — the Acts are ingested on
// dev only — so that was a false claim on the one page where money changes
// hands, and precisely the failure the derived-stats machinery in lib/api.ts was
// built to make impossible (/ and /products already derive their source lists;
// /pricing was left hand-typed). Deriving it means the page cannot lie today and
// picks the Acts up by itself the day they land on prod.
function tiers(stats: CorpusStats): Tier[] {
	const sources = corpusSourceProse(stats);
	const features: Record<PlanKey, string[]> = {
		solo: [
			"Unlimited research chat with cited, verified answers",
			// Degraded fetch (dev, no backend) → name no sources rather than print
			// an empty list as if it were a claim.
			sources
				? `Full search — Iowa ${sources}`
				: "Full search across the Iowa corpus",
			// Was "Citator with treatment & supersession notes". Treatment is real
			// and live: a deterministic classifier over the caselaw citation graph
			// (apps/corpus/services/treatment.py), cached per decision and already
			// shipped on /results. Supersession notes are NOT: CaseResearchNote.Kind
			// .ACT_SUPERSESSION is written by backfill_acts_code_edges from the
			// session-law amended table, so it is downstream of the Iowa Acts — and
			// prod has zero. Claim the half that is true.
			"Citator — negative-treatment flags on decisions",
			"MCP connector, saved research & the email assistant",
		],
		firm: [
			"Everything in Solo",
			"Brief cite-check with PDF & DOCX upload",
			"Org console — seats, roles & invitations",
			"Firm-wide usage dashboard & priority support",
		],
		enterprise: [
			"Everything in Firm",
			"Custom corpus & integrations",
			"SSO & onboarding",
			"Dedicated support",
		],
	};
	return PLANS.map((plan) => ({
		...plan,
		features: features[plan.key],
		featured: plan.key === "solo",
	}));
}

export default async function PricingPage() {
	const stats = await fetchCorpusStats();
	return (
		<CarbonPage>
			<PageHero
				eyebrow="Pricing"
				title="Simple pricing, honest terms."
				lede={
					BILLING_LIVE
						? "Every plan starts with a 7-day free trial — card up front, a reminder email before your first charge, cancel anytime during the trial."
						: `These are our launch prices, announced ahead of time as promised. ${BRAND_NAME} is still in open beta: billing hasn't started, and you'll get clear notice before anything is ever charged.`
				}
				actions={
					<>
						{BILLING_LIVE ? (
							<SolidLink href={`${APP_URL}/start`}>
								Start 7-day free trial
							</SolidLink>
						) : (
							<SolidLink href={APP_URL}>Get started</SolidLink>
						)}
						<HairlineLink href={`${CONSULTING_HREF}#contact`}>
							Talk to us
						</HairlineLink>
					</>
				}
			/>
			<Tiers stats={stats} />
			<Faq />
			<CtaBand />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// 01 — Tiers: one ruled tile row, hairline feature lists, CTA on the baseline
// ---------------------------------------------------------------------------

function Tiers({ stats }: { stats: CorpusStats }) {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="01"
					label="Plans"
					title="One product. Terms you can plan around."
				/>

				<div className="mt-14 grid divide-y divide-border border border-border lg:grid-cols-3 lg:divide-x lg:divide-y-0">
					{tiers(stats).map((t) => (
						<TierTile key={t.name} tier={t} />
					))}
				</div>

				<p className="mt-8 text-[13px] text-muted-foreground">
					"Unlimited" means fair professional use — generous monthly usage
					allowances, never a per-question meter.
					{!BILLING_LIVE &&
						" Prices take effect when billing launches; current beta users get clear notice well before any charge."}
				</p>
			</div>
		</section>
	);
}

function TierTile({ tier }: { tier: Tier }) {
	const muted = tier.cta.disabled;
	return (
		<div
			className={cn(
				"flex flex-col bg-card p-8",
				tier.featured && "border-t-[3px] border-t-[#0f62fe]",
			)}
		>
			<Eyebrow>{tier.badge ?? (muted ? "Planned" : "At launch")}</Eyebrow>
			<h2
				className={cn(
					"mt-5 font-light text-2xl",
					muted && "text-muted-foreground",
				)}
			>
				{tier.name}
			</h2>
			<div className="mt-4 flex items-baseline gap-1.5">
				<span
					className={cn(
						"font-light text-4xl tabular-nums",
						muted && "text-muted-foreground",
					)}
				>
					{tier.price}
				</span>
				{tier.cadence && (
					<span className="text-muted-foreground text-sm">{tier.cadence}</span>
				)}
			</div>
			{tier.subPrice && (
				<p className="mt-1.5 text-[13px] text-muted-foreground tabular-nums">
					{tier.subPrice}
				</p>
			)}
			<p className="mt-3 text-muted-foreground text-sm leading-relaxed">
				{tier.tagline}
			</p>

			<ul className="mt-8">
				{tier.features.map((f) => (
					<li
						key={f}
						className={cn(
							"flex items-start gap-2.5 border-border border-t py-3 text-sm",
							muted ? "text-muted-foreground" : "text-foreground/85",
						)}
					>
						<CheckIcon
							aria-hidden
							className="mt-0.5 size-4 shrink-0 text-muted-foreground"
							strokeWidth={1.75}
						/>
						{f}
					</li>
				))}
			</ul>

			<div className="mt-auto pt-10">
				{muted ? (
					<span className="inline-flex h-12 items-center border border-border px-4 text-muted-foreground text-sm">
						{tier.cta.label}
					</span>
				) : tier.featured ? (
					<SolidLink href={tier.cta.href}>{tier.cta.label}</SolidLink>
				) : (
					<HairlineLink href={tier.cta.href} tone="light">
						{tier.cta.label}
					</HairlineLink>
				)}
			</div>
		</div>
	);
}

// ---------------------------------------------------------------------------
// 02 — FAQ: ruled rows, no accordions
// ---------------------------------------------------------------------------

const FAQS: { q: string; a: string }[] = [
	{
		q: "How does the 7-day trial work?",
		a: "You enter a card up front and get full access to your plan for 7 days. We email you a reminder before the trial ends, and you can cancel in one click any time during it — cancel and you're never charged.",
	},
	{
		q: "What happens to beta access?",
		a: `Beta ends when billing launches. Everyone using ${BRAND_NAME} today will get clear written notice — weeks, not days — before anyone is charged. We promised pricing would be announced before launch; this page is that announcement.`,
	},
	{
		q: "Do you offer plans for firms?",
		a: "Yes — Firm is $149/month and includes 3 seats, with additional seats at $39/month each. You get an org console for seats, roles, and invitations, a firm-wide usage dashboard, and cite-check uploads. Adding a seat prorates automatically.",
	},
	{
		q: "Do you offer annual billing?",
		a: "Solo is $490/year — two months free. For firm annual billing or invoicing, talk to us and we'll set it up.",
	},
	// This used to promise that "statute, rule, and case pages stay publicly
	// readable." They are not: AuthGate's PUBLIC_PREFIXES covers neither /browse
	// nor /cases, so a signed-out visitor hits the sign-in wall. Opening them up
	// is a GTM decision, not a copy fix — until it is made, the page says what is
	// actually true.
	{
		q: "Do I need an account to read the law?",
		a: `Yes — ${BRAND_NAME} is an account-based product: signing in is what gets you the browse, search, and research surfaces. The official text of Iowa law is always free from the State, and every citation we return links straight back to it.`,
	},
	{
		q: "Is my research used to train models?",
		a: "No. Your questions and answers aren't used to train models, and chat traces are retained only briefly for reliability.",
	},
];

function Faq() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 pb-20 sm:px-8 lg:pb-28">
				<SectionHead n="02" label="Questions" title="Asked and answered." />

				<dl className="mt-14 grid gap-x-12 gap-y-10 sm:grid-cols-2">
					{FAQS.map((f) => (
						<div key={f.q} className="border-border border-t pt-5">
							<dt className="font-semibold text-[15px]">{f.q}</dt>
							<dd className="mt-2 max-w-md text-muted-foreground text-sm leading-relaxed">
								{f.a}
							</dd>
						</div>
					))}
				</dl>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// CTA band — left-aligned, declarative
// ---------------------------------------------------------------------------

function CtaBand() {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="flex flex-col gap-10 border-[#393939] border-t pt-10 lg:flex-row lg:items-end lg:justify-between">
					<div className="max-w-2xl">
						<h2 className="font-light text-3xl sm:text-4xl">Start today.</h2>
						<p className="mt-4 text-[#c6c6c6] text-lg leading-relaxed">
							{BILLING_LIVE
								? "Start your 7-day free trial. Ask your first question and follow the citation to the source."
								: "Beta access is open now. Ask your first question and follow the citation to the source."}
						</p>
					</div>
					<div className="flex shrink-0 flex-col gap-3 sm:flex-row">
						{BILLING_LIVE ? (
							<SolidLink href={`${APP_URL}/start`}>Start free trial</SolidLink>
						) : (
							<SolidLink href={APP_URL}>Get started</SolidLink>
						)}
						<HairlineLink href={`${CONSULTING_HREF}#contact`}>
							Talk to our team
						</HairlineLink>
					</div>
				</div>
			</div>
		</section>
	);
}
