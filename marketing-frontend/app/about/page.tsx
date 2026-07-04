// About page for the Hudson Legal Technologies marketing site (/about).
//
// Carbon (IBM design system) treatment: dark leadspace, alternating ink/light
// bands with numbered SectionHeads, hairline rules instead of cards. Company
// story + principles + founder. Server component (carries <metadata>).

import type { Metadata } from "next";
import {
	CarbonPage,
	Eyebrow,
	HairlineLink,
	INK,
	PageHero,
	SectionHead,
	SolidLink,
	TextLink,
} from "@/components/marketing/carbon";
import { CONSULTING_HREF } from "@/components/marketing/chrome";
import { APP_URL } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title: "About — Hudson Legal Technologies",
	description:
		"Hudson Legal Technologies builds grounded, citable AI research tools for practitioners — and helps teams adopt technology that holds up.",
};

export default function AboutPage() {
	return (
		<CarbonPage>
			<PageHero
				eyebrow="About"
				title="Legal AI you can actually trust."
				lede="Hudson Legal Technologies builds grounded, citable research tools for practitioners — and helps teams adopt technology that holds up in the real world."
			/>
			<Story />
			<Principles />
			<Founder />
			<CtaBand />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// 01 — Story
// ---------------------------------------------------------------------------

function Story() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="01"
					label="Why we exist"
					title="The law deserves better than a confident guess."
				/>

				<div className="mt-12 max-w-3xl space-y-5 text-[17px] text-foreground/85 leading-[1.75]">
					<p>
						General-purpose chatbots are fluent, and fluency is exactly the
						problem. They'll produce a citation that looks perfect and points at
						nothing. In most fields that's an annoyance. In law it's
						malpractice.
					</p>
					<p>
						Hudson started from a simple conviction: an answer about the law is
						only worth anything if you can trace it to the text. So we built the
						whole product around that — grounded retrieval from the effective
						text, real citations, and a verification step that checks every
						quote against the source before you ever see it.
					</p>
					<p>
						That discipline is also why teams ask us to help with the rest of
						their stack. Building software that has to be <em>right</em> is a
						transferable skill — so alongside the product, we consult on
						technology more broadly, from strategy to shipped systems.
					</p>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 02 — Principles: numbered grid on dark, matching home-2
// ---------------------------------------------------------------------------

const PRINCIPLES: { n: string; claim: string; body: string }[] = [
	{
		n: "01",
		claim: "Grounded by default.",
		body: "If the corpus doesn't support it, we don't say it. No answer beats a wrong one.",
	},
	{
		n: "02",
		claim: "Show your work.",
		body: "Every claim ties to text you can open and read. Trust is earned with receipts.",
	},
	{
		n: "03",
		claim: "Verify, don't hope.",
		body: "Determinism where it counts — citations checked by code, not graded by another model.",
	},
	{
		n: "04",
		claim: "Build, don't just advise.",
		body: "We ship our own product in production, and bring that same hands-on bar to every engagement.",
	},
];

function Principles() {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="02"
					label="What we believe"
					title="Principles we build by."
					tone="dark"
				/>

				<div className="mt-14 grid gap-x-12 gap-y-12 sm:grid-cols-2">
					{PRINCIPLES.map((p) => (
						<div key={p.n} className="border-[#393939] border-t pt-6">
							<span className="font-mono text-[#78a9ff] text-sm">{p.n}</span>
							<h3 className="mt-4 text-xl leading-snug">{p.claim}</h3>
							<p className="mt-3 max-w-md text-[#a8a8a8] text-[15px] leading-relaxed">
								{p.body}
							</p>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 03 — Founder: hairline-ruled block, no avatar
// ---------------------------------------------------------------------------

function Founder() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<div className="max-w-3xl border-border border-t pt-6">
					<Eyebrow>Founder</Eyebrow>
					<h3 className="mt-4 font-semibold text-2xl">Nick Hudson</h3>
					<p className="mt-4 text-[16px] text-muted-foreground leading-relaxed">
						Nick founded Hudson Legal Technologies to build research tools he'd
						actually trust with a citation. He writes about grounding,
						retrieval, and verification, and works directly with the firms and
						teams adopting AI the responsible way.
					</p>
					<div className="mt-6">
						<TextLink href={CONSULTING_HREF}>Work with us</TextLink>
					</div>
				</div>
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
						<h2 className="font-light text-3xl sm:text-4xl">
							See what grounded research feels like.
						</h2>
						<p className="mt-4 text-[#c6c6c6] text-lg leading-relaxed">
							In beta now. Ask a question, follow the citation to the source.
						</p>
					</div>
					<div className="flex shrink-0 flex-col gap-3 sm:flex-row">
						<SolidLink href={APP_URL}>Get started</SolidLink>
						<HairlineLink href={CONSULTING_HREF}>Talk to us</HairlineLink>
					</div>
				</div>
			</div>
		</section>
	);
}
