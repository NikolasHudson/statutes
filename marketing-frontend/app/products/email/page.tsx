// Product page for the Email assistant — verified legal research over plain
// email, in the Carbon register (see /products/corpus for the pattern).
//
// Copy is grounded in the shipped pipeline (backend/apps/mail): inbound mail
// is SPF/DKIM-checked, senders are allowlisted during the pilot, every reply
// passes the same deterministic verification gate as chat, citations are
// linked only when they resolve, and official PDFs attach only on request.
// The product is in pilot — the CTA is "request access", not sign-up.

import {
	BadgeCheckIcon,
	InboxIcon,
	LinkIcon,
	type LucideIcon,
	MailCheckIcon,
	PaperclipIcon,
	ShieldCheckIcon,
} from "lucide-react";
import type { Metadata } from "next";
import {
	CarbonPage,
	HairlineLink,
	INK,
	PageHero,
	SectionHead,
	SolidLink,
} from "@/components/marketing/carbon";
import { CONSULTING_HREF, CONTACT_HREF } from "@/components/marketing/chrome";
import { ProductFamily } from "@/components/marketing/product-family";
import { cn } from "@/lib/utils";

const ASSISTANT_ADDRESS = "assistant@mail.nick.law";

export const metadata: Metadata = {
	title: "Email assistant — Verified legal research in your inbox",
	description:
		"Email a legal question and get a verified, cited answer back. Citations linked to the source, official PDFs on request — the Hudson Corpus pipeline, in the tool every attorney already uses.",
};

export default function EmailProductPage() {
	return (
		<CarbonPage>
			<Hero />
			<ReplyShowcase />
			<HowItWorks />
			<TrustGrid />
			<CtaBand />
			<ProductFamily current="email" n="04" />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero() {
	return (
		<PageHero
			eyebrow="Products — Email assistant"
			title={
				<>
					Legal research that
					<br />
					answers your email.
				</>
			}
			lede={
				<>
					Send a question to{" "}
					<span className="font-mono text-[0.95em] text-white">
						{ASSISTANT_ADDRESS}
					</span>{" "}
					and a verified answer comes back — every citation checked against the
					effective text before the reply is sent, every resolved cite a link to
					its source. No new app. No new tab. Just email.
				</>
			}
			actions={
				<>
					<SolidLink href={CONTACT_HREF}>Request pilot access</SolidLink>
					<HairlineLink href="#how">How it works</HairlineLink>
				</>
			}
		/>
	);
}

// ---------------------------------------------------------------------------
// 01 — The reply is the product shot: a faithful mock of a real exchange
// ---------------------------------------------------------------------------

function ReplyShowcase() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-20">
				<figure className="border border-border bg-card">
					<figcaption className="flex items-center justify-between gap-4 border-border border-b px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
						<span className="truncate">
							Reply — verified answer with linked citations
						</span>
						<span className="shrink-0">{ASSISTANT_ADDRESS}</span>
					</figcaption>

					<div className="p-6 sm:p-10">
						{/* the attorney's message */}
						<div className="ml-auto max-w-xl border border-border bg-secondary/50 p-5">
							<p className="font-mono text-[11px] text-muted-foreground">
								To: {ASSISTANT_ADDRESS}
							</p>
							<p className="mt-1 font-mono text-[11px] text-muted-foreground">
								Subject: Dram shop — notice deadline?
							</p>
							<p className="mt-4 text-[14.5px] leading-relaxed">
								What's the written-notice deadline for an Iowa dram shop claim,
								and what happens if my client missed it?
							</p>
						</div>

						{/* the assistant's reply */}
						<div className="mt-6 max-w-2xl border border-border bg-background p-5 sm:p-7">
							<p className="font-mono text-[11px] text-muted-foreground">
								From: Hudson Corpus &lt;{ASSISTANT_ADDRESS}&gt;
							</p>
							<p className="mt-1 font-mono text-[11px] text-muted-foreground">
								Re: Dram shop — notice deadline?
							</p>
							<div className="mt-5 space-y-4 text-[14.5px] leading-relaxed">
								<p>
									Under{" "}
									<span className="text-[#0f62fe] underline underline-offset-2">
										Iowa Code § 123.93
									</span>
									, the injured person must give the licensee or permittee (or
									their insurance carrier) written notice of the intention to
									bring the action within six months of the occurrence of the
									injury,{" "}
									<em>
										"indicating the time, place and circumstances causing the
										injury."
									</em>
								</p>
								<p>
									The six-month period is extended only for the reasons the
									statute lists — incapacity, or inability through reasonable
									diligence to identify the responsible licensee. Where no
									timely notice was given and no extension applied, the claim
									was barred — see{" "}
									<span className="text-[#0f62fe] underline underline-offset-2">
										Berte v. Bode, 692 N.W.2d 368 (Iowa 2005)
									</span>
									…
								</p>
							</div>
							<p className="mt-6 border-border border-t pt-4 font-mono text-[11px] text-muted-foreground">
								✓ 2 of 2 citations · 1 of 1 quotes verified against the
								effective text · official PDFs available on request
							</p>
						</div>
					</div>
				</figure>
				<p className="mt-4 font-mono text-[11px] text-muted-foreground">
					Illustrative exchange. Replies carry both plain-text and HTML, and
					only citations that resolve to the corpus are linked.
				</p>
			</div>
		</section>
	);
}

// ---------------------------------------------------------------------------
// 02 — How it works
// ---------------------------------------------------------------------------

const STEPS: { n: string; title: string; body: string }[] = [
	{
		n: "1",
		title: "Ask like you'd ask a colleague",
		body: "Write the question in plain language and send it. Replies land in the same thread, and follow-ups keep their context — it's a conversation, not a form.",
	},
	{
		n: "2",
		title: "The corpus does the research",
		body: "Your question runs through the same grounded pipeline as Hudson Corpus — hybrid search over the Iowa Code, court rules, and caselaw, with answers built from the retrieved text.",
	},
	{
		n: "3",
		title: "The answer is verified, then sent",
		body: "Before the reply leaves, a deterministic gate checks every citation and quote against the source. Resolved citations become links; if a cite can't be verified, it is never dressed up as if it were.",
	},
];

function HowItWorks() {
	return (
		<section id="how" className={cn("scroll-mt-20 text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="02"
					label="How it works"
					title="From question to verified answer."
					tone="dark"
				/>
				<div className="mt-14 grid gap-px border border-[#393939] bg-[#393939] lg:grid-cols-3">
					{STEPS.map((s) => (
						<div key={s.n} className="bg-[#161616] p-8">
							<p className="font-mono text-[#78a9ff] text-[13px]">{s.n}</p>
							<h3 className="mt-4 font-semibold text-[16px]">{s.title}</h3>
							<p className="mt-3 text-[#c6c6c6] text-[14px] leading-relaxed">
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
// 03 — Why it can be trusted with email
// ---------------------------------------------------------------------------

type Trust = { icon: LucideIcon; title: string; body: string };

const TRUST: Trust[] = [
	{
		icon: BadgeCheckIcon,
		title: "Verified before it sends",
		body: "The same deterministic citation-and-quote gate as the app runs on every reply. An unverifiable answer doesn't go out claiming to be verified.",
	},
	{
		icon: LinkIcon,
		title: "Links only where they resolve",
		body: "Citations are linked only when they resolve to the corpus. A link is itself a trust signal — an unresolvable cite stays plain text.",
	},
	{
		icon: PaperclipIcon,
		title: "Official PDFs, on request",
		body: "Ask for the PDF of a section and the official publication comes attached. Attachments are opt-in — links are always offered.",
	},
	{
		icon: MailCheckIcon,
		title: "Authenticated inbound",
		body: "Inbound mail is SPF/DKIM-checked and loop-guarded before anything runs. Spoofed senders don't get answers.",
	},
	{
		icon: ShieldCheckIcon,
		title: "Allowlisted senders",
		body: "During the pilot, only approved senders receive answers — access is deliberate, per address, and revocable.",
	},
	{
		icon: InboxIcon,
		title: "Readable anywhere",
		body: "Every reply carries a clean plain-text version alongside the HTML, so it reads correctly in Outlook, Gmail, or a phone screen.",
	},
];

function TrustGrid() {
	return (
		<section className="bg-background">
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
				<SectionHead
					n="03"
					label="Built for the inbox"
					title="Email is casual. The answers aren't."
				/>
				<div className="mt-14 grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
					{TRUST.map((t) => {
						const Icon = t.icon;
						return (
							<div key={t.title} className="bg-card p-8">
								<Icon className="size-5" strokeWidth={1.5} aria-hidden />
								<h3 className="mt-6 font-semibold text-[15px]">{t.title}</h3>
								<p className="mt-2 text-[13.5px] text-muted-foreground leading-relaxed">
									{t.body}
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
// 04 — CTA band
// ---------------------------------------------------------------------------

function CtaBand() {
	return (
		<section className={cn("text-white", INK)}>
			<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-24">
				<div className="flex flex-col gap-10 border-[#393939] border-t pt-10 lg:flex-row lg:items-end lg:justify-between">
					<div className="max-w-2xl">
						<h2 className="font-light text-3xl sm:text-4xl">
							Put verified research where you already work.
						</h2>
						<p className="mt-4 text-[#c6c6c6] text-lg leading-relaxed">
							The email assistant is in pilot with Iowa practitioners. Tell us
							about your practice and we'll set your addresses up.
						</p>
					</div>
					<div className="flex shrink-0 flex-col gap-3 sm:flex-row">
						<SolidLink href={CONTACT_HREF}>Request pilot access</SolidLink>
						<HairlineLink href={CONSULTING_HREF}>
							Book a consultation
						</HairlineLink>
					</div>
				</div>
			</div>
		</section>
	);
}
