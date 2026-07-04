// Pricing page for the Hudson Legal Technologies marketing site (/pricing),
// in the Carbon (IBM design system) register — dark leadspace, hairline tier
// tiles, ruled FAQ rows, ink CTA band. Chrome + primitives come from
// components/marketing/carbon.tsx.
//
// Hudson is in beta, so "Beta access" is the live/highlighted tier and the paid
// tiers are shown as planned ("what pricing will look like"). Honest framing:
// pricing is announced before launch; nobody gets charged without notice.
// Server component (carries <metadata>).

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
import { APP_URL } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title: "Pricing — Hudson Legal Technologies",
	description:
		"Hudson is in beta. See what's included now and where pricing is headed — you won't be charged without notice.",
};

type Tier = {
	name: string;
	price: string;
	cadence?: string;
	tagline: string;
	features: string[];
	cta: { label: string; href: string; disabled?: boolean };
	featured?: boolean;
	badge?: string;
};

const TIERS: Tier[] = [
	{
		name: "Beta access",
		price: "In beta",
		tagline:
			"Full access today. Pricing is announced before launch — never a surprise charge.",
		features: [
			"Full corpus — Iowa Code, Court Rules & caselaw",
			"Grounded, cited answers with verification",
			"Hybrid search across all sources",
			"Use in the browser and via MCP",
		],
		cta: { label: "Get started", href: APP_URL },
		featured: true,
		badge: "Available now",
	},
	{
		name: "Pro",
		price: "$29",
		cadence: "/ month",
		tagline: "For the individual practitioner who lives in research.",
		features: [
			"Everything in Beta access",
			"Higher usage limits",
			"Priority answers & support",
			"Saved research & history",
		],
		cta: { label: "Coming soon", href: "#", disabled: true },
	},
	{
		name: "Team & Firm",
		price: "Custom",
		tagline: "For firms standardizing how the team uses AI.",
		features: [
			"Everything in Pro",
			"Seats, roles & SSO",
			"Custom corpus & integrations",
			"Onboarding & dedicated support",
		],
		cta: { label: "Talk to us", href: `${CONSULTING_HREF}#contact` },
	},
];

export default function PricingPage() {
	return (
		<CarbonPage>
			<PageHero
				eyebrow="Pricing — Now in beta"
				title="Simple pricing, honest terms."
				lede="Hudson is in open beta. Here's what's included today and where pricing is headed — you'll never be charged without notice."
				actions={
					<>
						<SolidLink href={APP_URL}>Get started</SolidLink>
						<HairlineLink href={`${CONSULTING_HREF}#contact`}>
							Talk to us
						</HairlineLink>
					</>
				}
			/>
			<Tiers />
			<Faq />
			<CtaBand />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// 01 — Tiers: one ruled tile row, hairline feature lists, CTA on the baseline
// ---------------------------------------------------------------------------

function Tiers() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="01"
					label="Plans"
					title="One product. Terms you can plan around."
				/>

				<div className="mt-14 grid divide-y divide-border border border-border lg:grid-cols-3 lg:divide-x lg:divide-y-0">
					{TIERS.map((t) => (
						<TierTile key={t.name} tier={t} />
					))}
				</div>

				<p className="mt-8 text-[13px] text-muted-foreground">
					Paid tiers are indicative while we're in beta and may change before
					launch. Current users will get plenty of notice.
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
		q: "What does beta access include?",
		a: "The full product — the whole corpus, cited answers, verification, and MCP access. We'll announce pricing before launch and give you plenty of notice before anything changes.",
	},
	{
		q: "What happens when beta ends?",
		a: "We'll introduce paid plans with clear notice well ahead of any change. You won't wake up to a surprise charge.",
	},
	{
		q: "Do you offer plans for firms?",
		a: "Yes — Team & Firm plans cover seats, SSO, a custom corpus, and onboarding. Reach out and we'll scope it with you.",
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
							Beta access is open now. Ask your first question and follow the
							citation to the source.
						</p>
					</div>
					<div className="flex shrink-0 flex-col gap-3 sm:flex-row">
						<SolidLink href={APP_URL}>Get started</SolidLink>
						<HairlineLink href={`${CONSULTING_HREF}#contact`}>
							Talk to our team
						</HairlineLink>
					</div>
				</div>
			</div>
		</section>
	);
}
