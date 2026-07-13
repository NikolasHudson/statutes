// Consulting / services page for Hudson Legal Technologies.
//
// Positioned as broad technology consulting (strategy, custom software, data,
// AI/automation, integrations, fractional CTO) — not narrowly grounded-AI.
// Hudson Corpus is used as proof that we ship real products, not as the scope.
//
// Carbon (IBM design system) treatment: dark leadspace, numbered sections
// alternating light/ink bands, hairline rules instead of cards. Server
// component (carries <metadata>); the contact form is a client component.

import { MailIcon } from "lucide-react";
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
import { ConsultForm } from "@/components/marketing/consult-form";
import { CONTACT_EMAIL } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title: "Consulting — Hudson Legal Technologies",
	description:
		"Pragmatic technology consulting — strategy, custom software, data, AI, and integrations. From the team that builds and ships its own products.",
};

export default function ConsultingPage() {
	return (
		<CarbonPage>
			<PageHero
				eyebrow="Consulting"
				title={
					<>
						Technology consulting
						<br />
						that ships.
					</>
				}
				lede="From strategy to working software, we help teams design, build, and adopt technology that holds up in the real world — software, data, AI, and the integrations that tie it all together. Practical engineering, not slideware."
				actions={
					<>
						<SolidLink href="#contact">Start a conversation</SolidLink>
						<HairlineLink href="#process">How we work</HairlineLink>
					</>
				}
			/>
			<Services />
			<WhoItsFor />
			<Process />
			<Contact />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// 01 — Services / engagements
// ---------------------------------------------------------------------------

const SERVICES: { n: string; title: string; body: string }[] = [
	{
		n: "01",
		title: "Technology strategy & roadmap",
		body: "Figure out what to build, what to buy, and what to ignore — a pragmatic plan tied to outcomes, not hype.",
	},
	{
		n: "02",
		title: "Custom software & product engineering",
		body: "Design and build web apps, internal tools, and products that are fast, maintainable, and ready for production.",
	},
	{
		n: "03",
		title: "Data & infrastructure",
		body: "Pipelines, storage, search, and the cloud plumbing that makes everything else possible — built to scale and to last.",
	},
	{
		n: "04",
		title: "AI & automation",
		body: "Apply AI and automation where they actually pay off — grounded, measurable, and safe, with a human in the loop where it counts.",
	},
	{
		n: "05",
		title: "Integration & APIs",
		body: "Connect the tools you already use. APIs, webhooks, and systems that finally talk to each other instead of fighting.",
	},
	{
		n: "06",
		title: "Fractional CTO & advisory",
		body: "Senior technical leadership on tap — architecture, hiring, vendor calls, and a steady hand when the stakes are high.",
	},
];

function Services() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="01"
					label="What we do"
					title="From idea to shipped, end to end."
				/>

				<p className="mt-12 max-w-2xl text-[17px] text-foreground/80 leading-[1.75]">
					We don't just advise — we build. Hudson Corpus, our own legal-AI
					product, runs in production today; we bring that same hands-on
					engineering to your stack. Engage us on a single piece or the whole
					arc.
				</p>

				<div className="mt-14 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
					{SERVICES.map((s) => (
						<div key={s.n} className="border-border border-t pt-5">
							<span className="font-mono text-[#0f62fe] text-sm">{s.n}</span>
							<h3 className="mt-4 font-semibold text-[15px]">{s.title}</h3>
							<p className="mt-2 text-[13.5px] text-muted-foreground leading-relaxed">
								{s.body}
							</p>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 02 — Who we work with
// ---------------------------------------------------------------------------

const AUDIENCES: { title: string; body: string }[] = [
	{
		title: "Founders & startups",
		body: "Get from idea to a real product without standing up a full engineering team first.",
	},
	{
		title: "Growing businesses",
		body: "Modernize the systems your business runs on — and stop losing time to tools that don't fit.",
	},
	{
		title: "Teams & firms",
		body: "Professional and in-house teams who want practical software and automation for how they actually work.",
	},
];

function WhoItsFor() {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="02"
					label="Who we work with"
					title="Teams that want to build, not just talk."
					tone="dark"
				/>

				<div className="mt-14 grid gap-x-12 gap-y-12 md:grid-cols-3">
					{AUDIENCES.map((a) => (
						<div key={a.title} className="border-[#393939] border-t pt-6">
							<h3 className="text-xl leading-snug">{a.title}</h3>
							<p className="mt-3 max-w-md text-[#a8a8a8] text-[15px] leading-relaxed">
								{a.body}
							</p>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 03 — How we work
// ---------------------------------------------------------------------------

const STEPS: { step: string; title: string; body: string }[] = [
	{
		step: "01",
		title: "Assess",
		body: "We learn your goals, systems, and constraints, and agree on what success actually looks like.",
	},
	{
		step: "02",
		title: "Design",
		body: "A concrete plan: scope, architecture, and how we'll measure that it works.",
	},
	{
		step: "03",
		title: "Build",
		body: "We implement in tight, reviewable steps — working software you can see early and often.",
	},
	{
		step: "04",
		title: "Enable",
		body: "We hand over something your team owns, understands, and can run without us.",
	},
];

function Process() {
	return (
		<section id="process" className="scroll-mt-20 bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="03"
					label="How we work"
					title="A clear path, no mystery."
				/>

				<div className="mt-14 grid divide-y divide-border border border-border lg:grid-cols-4 lg:divide-x lg:divide-y-0">
					{STEPS.map((s) => (
						<div key={s.step} className="bg-card p-8">
							<span className="font-mono text-[#0f62fe] text-sm">{s.step}</span>
							<h3 className="mt-4 text-2xl">{s.title}</h3>
							<p className="mt-3 text-[15px] text-muted-foreground leading-relaxed">
								{s.body}
							</p>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 04 — Contact
// ---------------------------------------------------------------------------

function Contact() {
	return (
		<section id="contact" className={cn("scroll-mt-20 text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="04"
					label="Get in touch"
					title="Tell us what you're building."
					tone="dark"
				/>

				<div className="mt-14 grid gap-14 lg:grid-cols-[1fr_1.1fr] lg:gap-20">
					{/* Left — pitch */}
					<div>
						<p className="max-w-xl text-[#c6c6c6] text-lg leading-relaxed">
							Tell us what you're trying to do. We'll tell you honestly whether
							we can help, what it would take, and where to start.
						</p>

						<div className="mt-10 space-y-8">
							<ExpectItem n="01" title="A real conversation">
								No scripted demo — a working discussion about your specific
								situation.
							</ExpectItem>
							<ExpectItem n="02" title="Honest scoping">
								If a project isn't worth doing yet, we'll tell you that too.
							</ExpectItem>
							<ExpectItem n="03" title="A clear next step">
								You leave with a concrete recommendation, whether or not we work
								together.
							</ExpectItem>
						</div>

						<div className="mt-10 border-[#393939] border-t pt-6">
							<Eyebrow tone="dark">Prefer email?</Eyebrow>
							<a
								href={`mailto:${CONTACT_EMAIL}`}
								className="mt-3 inline-flex items-center gap-2 font-medium text-[#78a9ff] text-sm hover:underline"
							>
								<MailIcon className="size-4" />
								{CONTACT_EMAIL}
							</a>
						</div>
					</div>

					{/* Right — form */}
					<ConsultForm />
				</div>
			</div>
		</section>
	);
}

function ExpectItem({
	n,
	title,
	children,
}: {
	n: string;
	title: string;
	children: React.ReactNode;
}) {
	return (
		<div className="border-[#393939] border-t pt-5">
			<span className="font-mono text-[#78a9ff] text-sm">{n}</span>
			<p className="mt-3 max-w-md text-[#c6c6c6] text-[15px] leading-relaxed">
				<span className="font-semibold text-white">{title}.</span> {children}
			</p>
		</div>
	);
}
