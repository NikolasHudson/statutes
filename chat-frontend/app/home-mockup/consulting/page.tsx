// Consulting / services page for Hudson Legal Tech.
//
// Positioned as broad technology consulting (strategy, custom software, data,
// AI/automation, integrations, fractional CTO) — not narrowly grounded-AI.
// Hudson Corpus is used as proof that we ship real products, not as the scope.
//
// Under the marketing tree (/home-mockup/consulting), shared site chrome.
// Server component (carries <metadata>); interactive bits are the nav and the
// contact form, both client components imported in.

import {
	ArrowRightIcon,
	BriefcaseIcon,
	Code2Icon,
	CompassIcon,
	DatabaseIcon,
	type LucideIcon,
	MailIcon,
	PlugZapIcon,
	SparklesIcon,
} from "lucide-react";
import type { Metadata } from "next";
import {
	gridTexture,
	navyBackdrop,
	SiteFooter,
	SiteNav,
} from "@/components/marketing/chrome";
import { ConsultForm } from "@/components/marketing/consult-form";

export const metadata: Metadata = {
	title: "Consulting — Hudson Legal Tech",
	description:
		"Pragmatic technology consulting — strategy, custom software, data, AI, and integrations. From the team that builds and ships its own products.",
};

export default function ConsultingPage() {
	return (
		<div className="min-h-dvh bg-background text-foreground">
			<SiteNav />
			<Hero />
			<Services />
			<WhoItsFor />
			<Process />
			<Contact />
			<SiteFooter />
		</div>
	);
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero() {
	return (
		<section
			className="relative overflow-hidden text-white"
			style={navyBackdrop}
		>
			<div aria-hidden className="absolute inset-0" style={gridTexture} />
			<div
				aria-hidden
				className="absolute inset-x-0 bottom-0 h-24"
				style={{
					backgroundImage:
						"linear-gradient(to bottom, rgba(11,28,48,0), var(--color-background))",
				}}
			/>
			<div className="relative mx-auto max-w-3xl px-5 py-20 text-center sm:px-8 lg:py-28">
				<p className="font-semibold text-[12px] text-white/70 uppercase tracking-[0.18em]">
					Consulting
				</p>
				<h1 className="mt-3 font-bold text-4xl leading-[1.1] tracking-tight sm:text-5xl">
					Technology consulting that ships
				</h1>
				<p className="mx-auto mt-5 max-w-xl text-lg text-white/75 leading-relaxed">
					From strategy to working software, we help teams design, build, and
					adopt technology that holds up in the real world — software, data, AI,
					and the integrations that tie it all together. Practical engineering,
					not slideware.
				</p>
				<div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
					<a
						href="#contact"
						className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-white px-6 font-medium text-[#11243d] text-sm transition-colors hover:bg-white/90"
					>
						Start a conversation
						<ArrowRightIcon className="size-4" />
					</a>
					<a
						href="#process"
						className="inline-flex h-10 items-center justify-center rounded-md border border-white/30 px-6 font-medium text-sm text-white transition-colors hover:bg-white/10"
					>
						How we work
					</a>
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Services / engagements
// ---------------------------------------------------------------------------

type Service = { icon: LucideIcon; title: string; body: string };

const SERVICES: Service[] = [
	{
		icon: CompassIcon,
		title: "Technology strategy & roadmap",
		body: "Figure out what to build, what to buy, and what to ignore — a pragmatic plan tied to outcomes, not hype.",
	},
	{
		icon: Code2Icon,
		title: "Custom software & product engineering",
		body: "Design and build web apps, internal tools, and products that are fast, maintainable, and ready for production.",
	},
	{
		icon: DatabaseIcon,
		title: "Data & infrastructure",
		body: "Pipelines, storage, search, and the cloud plumbing that makes everything else possible — built to scale and to last.",
	},
	{
		icon: SparklesIcon,
		title: "AI & automation",
		body: "Apply AI and automation where they actually pay off — grounded, measurable, and safe, with a human in the loop where it counts.",
	},
	{
		icon: PlugZapIcon,
		title: "Integration & APIs",
		body: "Connect the tools you already use. APIs, webhooks, and systems that finally talk to each other instead of fighting.",
	},
	{
		icon: BriefcaseIcon,
		title: "Fractional CTO & advisory",
		body: "Senior technical leadership on tap — architecture, hiring, vendor calls, and a steady hand when the stakes are high.",
	},
];

function Services() {
	return (
		<section className="scroll-mt-20">
			<div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="max-w-2xl">
					<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
						What we do
					</span>
					<h2 className="mt-3 font-bold text-3xl tracking-tight sm:text-4xl">
						From idea to shipped, end to end
					</h2>
					<p className="mt-4 text-lg text-muted-foreground leading-relaxed">
						We don't just advise — we build. Hudson Corpus, our own legal-AI
						product, runs in production today; we bring that same hands-on
						engineering to your stack. Pick a single piece or the whole arc.
					</p>
				</div>

				<div className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
					{SERVICES.map((s) => {
						const Icon = s.icon;
						return (
							<div key={s.title} className="bg-card p-7">
								<div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
									<Icon className="size-5.5" />
								</div>
								<h3 className="mt-5 font-semibold text-lg tracking-tight">
									{s.title}
								</h3>
								<p className="mt-2 text-[14px] text-muted-foreground leading-relaxed">
									{s.body}
								</p>
							</div>
						);
					})}
				</div>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// Who it's for
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
		<section className="border-border border-y bg-card">
			<div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="max-w-2xl">
					<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
						Who we work with
					</span>
					<h2 className="mt-3 font-bold text-3xl tracking-tight sm:text-4xl">
						Teams that want to build, not just talk
					</h2>
				</div>
				<div className="mt-10 grid gap-6 md:grid-cols-3">
					{AUDIENCES.map((a) => (
						<div
							key={a.title}
							className="rounded-2xl border border-border bg-background p-6"
						>
							<h3 className="font-semibold text-lg tracking-tight">
								{a.title}
							</h3>
							<p className="mt-2 text-[14px] text-muted-foreground leading-relaxed">
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
// How we work
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
		<section id="process" className="scroll-mt-20">
			<div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="max-w-2xl">
					<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
						How we work
					</span>
					<h2 className="mt-3 font-bold text-3xl tracking-tight sm:text-4xl">
						A clear path, no mystery
					</h2>
				</div>
				<div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
					{STEPS.map((s) => (
						<div
							key={s.step}
							className="rounded-2xl border border-border bg-card p-6"
						>
							<span className="font-bold text-4xl text-primary/25 tabular-nums">
								{s.step}
							</span>
							<h3 className="mt-3 font-semibold text-lg tracking-tight">
								{s.title}
							</h3>
							<p className="mt-2 text-[14px] text-muted-foreground leading-relaxed">
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
// Contact
// ---------------------------------------------------------------------------

function Contact() {
	return (
		<section
			id="contact"
			className="scroll-mt-20 border-border border-t bg-card"
		>
			<div className="mx-auto grid max-w-6xl gap-12 px-5 py-20 sm:px-8 lg:grid-cols-[1fr_1.1fr] lg:gap-16 lg:py-24">
				{/* Left — pitch */}
				<div>
					<span className="font-semibold text-[12px] text-primary uppercase tracking-[0.16em]">
						Get in touch
					</span>
					<h2 className="mt-3 font-bold text-3xl tracking-tight sm:text-4xl">
						Let's talk about what you're building
					</h2>
					<p className="mt-4 text-lg text-muted-foreground leading-relaxed">
						Tell us what you're trying to do. We'll tell you honestly whether we
						can help, what it would take, and where to start.
					</p>

					<div className="mt-8 space-y-4">
						<ExpectItem title="A real conversation">
							No scripted demo — a working discussion about your specific
							situation.
						</ExpectItem>
						<ExpectItem title="Honest scoping">
							If a project isn't worth doing yet, we'll tell you that too.
						</ExpectItem>
						<ExpectItem title="A clear next step">
							You leave with a concrete recommendation, whether or not we work
							together.
						</ExpectItem>
					</div>

					<div className="mt-8 flex items-center gap-3 border-border border-t pt-6">
						<span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
							<MailIcon className="size-4.5" />
						</span>
						<div className="text-sm">
							<div className="text-muted-foreground">Prefer email?</div>
							<a
								href="mailto:consulting@hudsonlegal.tech"
								className="font-medium text-primary hover:underline"
							>
								consulting@hudsonlegal.tech
							</a>
						</div>
					</div>
				</div>

				{/* Right — form */}
				<ConsultForm />
			</div>
		</section>
	);
}

function ExpectItem({
	title,
	children,
}: {
	title: string;
	children: React.ReactNode;
}) {
	return (
		<div className="flex items-start gap-3">
			<span className="mt-1 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
				<ArrowRightIcon className="size-3" />
			</span>
			<p className="text-[15px] text-foreground/85 leading-relaxed">
				<span className="font-semibold text-foreground">{title}.</span>{" "}
				{children}
			</p>
		</div>
	);
}
