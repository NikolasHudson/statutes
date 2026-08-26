// Product page for the Email assistant — verified legal research over plain
// email, on the ibm.com-style product shell
// (components/marketing/product-page.tsx): breadcrumb, a leadspace whose H1 is
// the product's name, a sticky in-page nav, then Overview → How it works →
// Built for the inbox → Use cases → Access.
//
// Copy is grounded in the shipped pipeline (backend/apps/mail): inbound mail
// is SPF/DKIM-checked, senders are allowlisted during the pilot, every reply
// passes the same deterministic verification gate as chat, citations are
// linked only when they resolve, and official PDFs attach only on request.
// The product is in pilot — the CTA is "request access", not sign-up, and
// there is no Pricing band here for the same reason: access is granted per
// address, not bought.
//
// The pilot is genuinely LIMITED (a handful of allowlisted addresses, all ours
// so far). Nothing on this page may imply a body of third-party users we do not
// have: say "access is granted per address", never "in pilot with practitioners".

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
	SolidLink,
} from "@/components/marketing/carbon";
import {
	CONSULTING_HREF,
	CONTACT_HREF,
	PRICING_HREF,
	PRODUCT_HREF,
} from "@/components/marketing/chrome";
import { ProductFamily } from "@/components/marketing/product-family";
import {
	NextStep,
	ProductLeadspace,
	ProductSection,
	type UseCase,
	UseCaseGrid,
} from "@/components/marketing/product-page";
import {
	ProductSubnav,
	type SubnavSection,
} from "@/components/marketing/product-subnav";
import { ASSISTANT_ADDRESS } from "@/lib/site";

export const metadata: Metadata = {
	title: "Email assistant — Verified legal research in your inbox",
	description:
		"Email a legal question and get a verified, cited answer back. Citations linked to the source, official PDFs on request — the Hudson Corpus pipeline, in the tool every attorney already uses.",
};

const PRODUCT = "Email assistant";

const SECTIONS: SubnavSection[] = [
	{ id: "overview", label: "Overview" },
	{ id: "how-it-works", label: "How it works" },
	{ id: "inbox", label: "Built for the inbox" },
	{ id: "use-cases", label: "Use cases" },
	{ id: "access", label: "Access" },
];

export default function EmailProductPage() {
	return (
		<CarbonPage>
			<ProductLeadspace
				product={PRODUCT}
				tagline="Legal research that answers your email."
				lede={
					<>
						Send a question to{" "}
						<span className="font-mono text-[0.95em] text-white">
							{ASSISTANT_ADDRESS}
						</span>{" "}
						and a verified answer comes back — every citation checked against
						the effective text before the reply is sent, every resolved cite a
						link to its source. No new app. No new tab. Just email.
					</>
				}
				actions={
					<>
						<SolidLink href={CONTACT_HREF}>Request pilot access</SolidLink>
						<HairlineLink href="#how-it-works">How it works</HairlineLink>
					</>
				}
				visual={<ComposeCard />}
			/>
			<ProductSubnav product={PRODUCT} sections={SECTIONS} />
			<Overview />
			<HowItWorks />
			<Inbox />
			<UseCases />
			<Access />
			<NextStep
				title="Put verified research where you already work."
				body="The email assistant is in limited pilot — access is granted per address. Tell us about your practice and we'll set your addresses up."
				actions={
					<>
						<SolidLink href={CONTACT_HREF}>Request pilot access</SolidLink>
						<HairlineLink href={CONSULTING_HREF}>
							Book a consultation
						</HairlineLink>
					</>
				}
				explore={[
					{ label: "Hudson Corpus", href: PRODUCT_HREF },
					{ label: "Pricing", href: PRICING_HREF },
					{ label: "Consulting", href: CONSULTING_HREF },
					{ label: "Contact us", href: CONTACT_HREF },
				]}
			/>
			<ProductFamily current="email" />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Leadspace visual — the half of the exchange you write. The answer it comes
// back with is the Overview's mock, below.
// ---------------------------------------------------------------------------

const QUESTION =
	"What's the written-notice deadline for an Iowa dram shop claim, and what happens if my client missed it?";

function ComposeCard() {
	return (
		<figure className="border border-[#393939] bg-card text-foreground">
			<figcaption className="flex items-center justify-between gap-4 border-border border-b px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
				<span className="truncate">New message</span>
				<span className="shrink-0">Send</span>
			</figcaption>
			<div className="p-6 sm:p-8">
				<p className="border-border border-b pb-3 font-mono text-[12px] text-muted-foreground">
					To: <span className="text-foreground">{ASSISTANT_ADDRESS}</span>
				</p>
				<p className="mt-3 border-border border-b pb-3 font-mono text-[12px] text-muted-foreground">
					Subject:{" "}
					<span className="text-foreground">Dram shop — notice deadline?</span>
				</p>
				<p className="mt-5 text-[15px] leading-relaxed">{QUESTION}</p>
				<p className="mt-8 border-border border-t pt-4 font-mono text-[11px] text-muted-foreground">
					A verified reply comes back to this thread — citations linked, quotes
					checked against the effective text.
				</p>
			</div>
		</figure>
	);
}

// ---------------------------------------------------------------------------
// Overview — the reply is the product shot: a faithful mock of an exchange
// ---------------------------------------------------------------------------

function ReplyShowcase() {
	return (
		<>
			<figure className="mt-14 border border-border bg-card">
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
						<p className="mt-4 text-[14.5px] leading-relaxed">{QUESTION}</p>
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
								diligence to identify the responsible licensee. Where no timely
								notice was given and no extension applied, the claim was barred
								— see{" "}
								<span className="text-[#0f62fe] underline underline-offset-2">
									Berte v. Bode, 692 N.W.2d 368 (Iowa 2005)
								</span>
								…
							</p>
						</div>
						<p className="mt-6 border-border border-t pt-4 font-mono text-[11px] text-muted-foreground">
							✓ 2 of 2 citations · 1 of 1 quotes verified against the effective
							text · official PDFs available on request
						</p>
					</div>
				</div>
			</figure>
			<p className="mt-4 font-mono text-[11px] text-muted-foreground">
				Illustrative exchange. Replies carry both plain-text and HTML, and only
				citations that resolve to the corpus are linked.
			</p>
		</>
	);
}

function Overview() {
	return (
		<ProductSection
			id="overview"
			label="Overview"
			title="The same verified research, by reply."
			intro="Everything the research product does — grounded retrieval over the Iowa corpus, a deterministic check on every quote and citation — reached by writing the question the way you'd write it to a colleague, and reading the answer where the rest of your work already arrives."
		>
			<ReplyShowcase />
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// How it works
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
		<ProductSection
			id="how-it-works"
			tone="dark"
			label="How it works"
			title="From question to verified answer."
		>
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
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Built for the inbox
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

function Inbox() {
	return (
		<ProductSection
			id="inbox"
			tone="layer"
			label="Built for the inbox"
			title="Email is casual. The answers aren't."
		>
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
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Use cases
// ---------------------------------------------------------------------------

const USE_CASES: UseCase[] = [
	{
		audience: "Between hearings",
		title: "A question from the courthouse steps.",
		body: "Mail from a phone and read the answer the same way — no app to install on a device you were not planning to research from.",
	},
	{
		audience: "Delegated research",
		title: "Forward the question, keep the thread.",
		body: "The exchange lives in the matter's own thread, where it can be filed with everything else about the case rather than trapped in a chat history.",
	},
	{
		audience: "Quick checks",
		title: "One provision, one answer, no session.",
		body: "For the deadline you half-remember, a reply with the section quoted and linked beats opening a research tool and rebuilding your context.",
	},
];

function UseCases() {
	return (
		<ProductSection
			id="use-cases"
			tone="dark"
			label="Use cases"
			title="When email is the right window."
		>
			<UseCaseGrid items={USE_CASES} tone="dark" />
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Access — no pricing band: the pilot is granted per address, not sold
// ---------------------------------------------------------------------------

function Access() {
	return (
		<ProductSection
			id="access"
			label="Access"
			title="Granted per address, while it's a pilot."
			intro="The assistant answers allowlisted senders only. That is a deliberate limit, not a waitlist gimmick: every address is added by hand, and it is the same control that keeps a spoofed sender from ever getting an answer."
			link={{ label: "See plans & pricing", href: PRICING_HREF }}
		>
			<div className="mt-14 grid gap-px border border-border bg-border sm:grid-cols-3">
				{[
					{
						title: "Tell us the addresses",
						body: "Which mailboxes should be able to ask — yours, your assistant's, the firm's shared inbox.",
					},
					{
						title: "We add them by hand",
						body: "Each address is allowlisted individually and can be removed the same way, at any time.",
					},
					{
						title: "Write to the assistant",
						body: `Send the first question to ${ASSISTANT_ADDRESS} and the verified reply comes back to the same thread.`,
					},
				].map((s, i) => (
					<div key={s.title} className="bg-card p-8">
						<p className="font-mono text-[#0f62fe] text-[13px]">{i + 1}</p>
						<h3 className="mt-4 font-semibold text-[16px]">{s.title}</h3>
						<p className="mt-3 text-[14px] text-muted-foreground leading-relaxed">
							{s.body}
						</p>
					</div>
				))}
			</div>
		</ProductSection>
	);
}
