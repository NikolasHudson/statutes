// Product page for Hudson EDMSpro — the court-filing extension, on the
// ibm.com-style product shell (components/marketing/product-page.tsx):
// breadcrumb, a leadspace whose H1 is the product's name, a sticky in-page nav,
// then Overview → How it works → Custody → Use cases → Pricing → next step.
//
// Copy is grounded in what shipped (backend/apps/edms + edms-extension/), and
// v1's boundary is Nick's 2026-07-28 scope cut: sign in, preview filings in
// the side panel, and download locally under server-defined naming rules.
// The whole OneDrive leg is PARKED behind EDMS_CLOUD_ENABLED (off) — so cloud
// saving may only ever appear here as "next", never as a live capability.
//
// Three claims this page must NOT make: (1) that the extension is on the
// Chrome Web Store — the listing is not published yet, so the CTA is "request
// early access", not "install"; (2) that saves to OneDrive work today — see
// above; (3) anything about the contributed-filings library — that is an
// in-app, explicit-consent surface, not a marketing point.

import {
	CloudUploadIcon,
	DownloadIcon,
	EyeIcon,
	FileTextIcon,
	KeyRoundIcon,
	type LucideIcon,
	ServerOffIcon,
	ShieldCheckIcon,
} from "lucide-react";
import type { Metadata } from "next";
import {
	CarbonPage,
	HairlineLink,
	SolidLink,
} from "@/components/marketing/carbon";
import {
	CONTACT_HREF,
	PRICING_HREF,
	PRODUCT_HREF,
} from "@/components/marketing/chrome";
import { ProductFamily } from "@/components/marketing/product-family";
import {
	NextStep,
	PlanBand,
	ProductLeadspace,
	ProductSection,
	type UseCase,
	UseCaseGrid,
} from "@/components/marketing/product-page";
import {
	ProductSubnav,
	type SubnavSection,
} from "@/components/marketing/product-subnav";
import { EDMS_PRODUCT_NAME } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title: "Hudson EDMSpro — Iowa court filings, filed where they belong",
	description:
		"A Chrome extension for Iowa's EDMS: preview filings in a panel beside the docket and download them — one or all — under clean, consistent names. One-click saves to your own cloud are next, designed so documents never pass through Hudson's servers.",
};

const SECTIONS: SubnavSection[] = [
	{ id: "overview", label: "Overview" },
	{ id: "how-it-works", label: "How it works" },
	{ id: "custody", label: "Custody" },
	{ id: "use-cases", label: "Use cases" },
	{ id: "pricing", label: "Pricing" },
];

export default function EdmsProductPage() {
	return (
		<CarbonPage>
			<ProductLeadspace
				product={EDMS_PRODUCT_NAME}
				tagline="Court filings, filed where they belong."
				lede="A Chrome extension for Iowa's EDMS. Preview any filing in a panel beside the docket, then download it — one or all — under clean, consistent names instead of the court's opaque ones."
				actions={
					<>
						<SolidLink href={CONTACT_HREF}>Request early access</SolidLink>
						<HairlineLink href="#how-it-works">How it works</HairlineLink>
					</>
				}
				visual={<NamingCard />}
			/>
			<ProductSubnav product={EDMS_PRODUCT_NAME} sections={SECTIONS} />
			<Overview />
			<HowItWorks />
			<Custody />
			<UseCases />
			<Pricing />
			<NextStep
				title="Filing management, included with your plan."
				body="Hudson EDMSpro is rolling out now, included with Solo and Firm plans — the Chrome Web Store listing is on its way. Tell us about your practice and we'll set you up early."
				actions={
					<>
						<SolidLink href={CONTACT_HREF}>Request early access</SolidLink>
						<HairlineLink href={PRICING_HREF}>See pricing</HairlineLink>
					</>
				}
				explore={[
					{ label: "Pricing", href: PRICING_HREF },
					{ label: "Hudson Corpus", href: PRODUCT_HREF },
					{ label: "Contact us", href: CONTACT_HREF },
				]}
			/>
			<ProductFamily current="edms" />
		</CarbonPage>
	);
}

// ---------------------------------------------------------------------------
// Leadspace visual — the naming rule, rendered
// ---------------------------------------------------------------------------

// The template and the filename below are the SHIPPED defaults, not a mockup
// flourish: DEFAULT_NAMING_TEMPLATE in backend/apps/edms/models.py is
// "{date}_{case_num}_{doc_title}", and render_filename (edms/routing.py)
// substitutes the scraped docket metadata into exactly that shape. If the
// default template changes, this card is wrong — it is quoting code.
const NAMING_TEMPLATE = "{date}_{case_num}_{doc_title}";
const SAVED_AS = "2026-07-14_LACL045678_Order - Trial Scheduling.pdf";

function NamingCard() {
	return (
		<figure className="border border-[#393939] bg-card text-foreground">
			<figcaption className="flex items-center justify-between gap-4 border-border border-b px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
				<span className="truncate">Naming — your template, every download</span>
				<span className="shrink-0">iowacourts.state.ia.us</span>
			</figcaption>
			<div className="p-6 sm:p-8">
				<p className="font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
					Your naming rule
				</p>
				<p className="mt-3 break-all font-mono text-[14px] text-[#0f62fe]">
					{NAMING_TEMPLATE}
				</p>
				<div className="mt-6 border-border border-t pt-6">
					<p className="font-mono text-[11px] text-muted-foreground uppercase tracking-[0.18em]">
						Every filing you download
					</p>
					<p className="mt-3 flex items-start gap-2 font-mono text-[13.5px] leading-relaxed">
						<DownloadIcon
							className="mt-0.5 size-3.5 shrink-0 text-[#24a148]"
							strokeWidth={1.5}
							aria-hidden
						/>
						<span className="break-all">{SAVED_AS}</span>
					</p>
					<p className="mt-4 text-[13px] text-muted-foreground leading-relaxed">
						Set it once in your account. Every download — including Download all
						— comes out named the same way.
					</p>
				</div>
			</div>
		</figure>
	);
}

// ---------------------------------------------------------------------------
// Overview — the docket is the product shot: filing rows with EDMSpro's
// actions, and the side panel rendering the preview beside them
// ---------------------------------------------------------------------------

const DOCKET_ROWS: {
	date: string;
	title: string;
	kind: string;
	active?: boolean;
}[] = [
	{
		date: "07/14/2026",
		title: "Order — Trial Scheduling",
		kind: "Order",
		active: true,
	},
	{
		date: "07/11/2026",
		title: "Answer and Affirmative Defenses",
		kind: "Answer",
	},
	{
		date: "06/30/2026",
		title: "Original Notice and Petition",
		kind: "Petition",
	},
	{ date: "06/30/2026", title: "Appearance — Defendant", kind: "Appearance" },
];

function RowActions({ active }: { active?: boolean }) {
	return (
		<span className="flex shrink-0 items-center gap-1.5">
			<span
				className={cn(
					"flex size-7 items-center justify-center border",
					active
						? "border-[#0f62fe] bg-[#0f62fe] text-white"
						: "border-border text-muted-foreground",
				)}
			>
				<EyeIcon className="size-4" strokeWidth={1.5} aria-hidden />
			</span>
			<span className="flex size-7 items-center justify-center border border-border text-muted-foreground">
				<DownloadIcon className="size-4" strokeWidth={1.5} aria-hidden />
			</span>
		</span>
	);
}

function DocketShowcase() {
	return (
		<>
			<figure className="mt-14 border border-border bg-card">
				<figcaption className="flex items-center justify-between gap-4 border-border border-b px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
					<span className="truncate">
						Hudson EDMSpro — on the docket, in the side panel
					</span>
					<span className="shrink-0">iowacourts.state.ia.us</span>
				</figcaption>

				<div className="grid lg:grid-cols-[1.5fr_1fr]">
					{/* the court's filing list, with EDMSpro's per-row actions */}
					<div className="p-6 sm:p-8">
						<p className="font-mono text-[11px] text-muted-foreground">
							Filings — LACL045678 · Smith v. Cedar Rapids Mut.
						</p>
						<ul className="mt-4 border-border border-t">
							{DOCKET_ROWS.map((r) => (
								<li
									key={r.title}
									className={cn(
										"flex items-center justify-between gap-4 border-border border-b px-1 py-3.5",
										r.active && "bg-secondary/50",
									)}
								>
									<span className="min-w-0">
										<span className="block truncate text-[14px]">
											{r.title}
										</span>
										<span className="mt-0.5 block font-mono text-[11px] text-muted-foreground">
											{r.date} · {r.kind}
										</span>
									</span>
									<RowActions active={r.active} />
								</li>
							))}
						</ul>
						<p className="mt-4 flex items-center gap-2 font-mono text-[11px] text-[#24a148]">
							<DownloadIcon
								className="size-3.5 shrink-0"
								strokeWidth={1.5}
								aria-hidden
							/>
							Downloaded — {SAVED_AS}
						</p>
					</div>

					{/* the side panel: preview + download, beside the docket */}
					<div className="border-border border-t lg:border-t-0 lg:border-l">
						<div className="flex items-center justify-between border-border border-b px-5 py-3">
							<span className="font-semibold text-[13px]">Hudson EDMSpro</span>
							<span className="font-mono text-[11px] text-muted-foreground">
								Signed in ✓
							</span>
						</div>
						<div className="p-5">
							<div className="flex aspect-[4/5] flex-col items-center justify-center gap-3 border border-border bg-background">
								<FileTextIcon
									className="size-8 text-muted-foreground"
									strokeWidth={1}
									aria-hidden
								/>
								<p className="px-6 text-center font-mono text-[11px] text-muted-foreground leading-relaxed">
									Order — Trial Scheduling.pdf
									<br />
									rendered in your browser
								</p>
							</div>
							<div className="mt-4 flex flex-col gap-2">
								<span className="flex h-9 items-center justify-center bg-[#0f62fe] font-medium text-[13px] text-white">
									Download
								</span>
							</div>
						</div>
					</div>
				</div>
			</figure>
			<p className="mt-4 font-mono text-[11px] text-muted-foreground">
				Illustrative docket. EDMSpro adds the preview and download actions to
				the court's own filing rows; the PDF renders in a panel beside the
				docket, so the list stays in view.
			</p>
		</>
	);
}

function Overview() {
	return (
		<ProductSection
			id="overview"
			label="Overview"
			title="The docket, without the downloads folder."
			intro="Iowa's EDMS makes you open a filing to find out what it is, and hands it back under a name you cannot read. EDMSpro puts a preview and a download on every row of the court's own docket, and names what you save the way your files are named."
		>
			<DocketShowcase />
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// How it works
// ---------------------------------------------------------------------------

const STEPS: { n: string; title: string; body: string }[] = [
	{
		n: "1",
		title: "Sign in from the side panel",
		body: "Add the extension and sign in with your Hudson account — a standard OAuth consent, with nothing typed into the extension itself. Your naming rules live in your account settings; set them once.",
	},
	{
		n: "2",
		title: "Work the docket as usual",
		body: "EDMSpro adds preview and download to every filing row on Iowa's EDMS. Click the eye and the PDF opens in a panel beside the docket — no downloads-folder detour, no tab juggling, no losing your place.",
	},
	{
		n: "3",
		title: "Download it, named right",
		body: "One click saves the filing under a clean, consistent name — case number, date, document type — and Download all grabs every filing on the docket at once, ready to file where they belong.",
	},
];

function HowItWorks() {
	return (
		<ProductSection
			id="how-it-works"
			tone="dark"
			label="How it works"
			title="From docket to filed, in one click."
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
// Custody — why a filing tool can be trusted with filings
// ---------------------------------------------------------------------------

type Custody = { icon: LucideIcon; title: string; body: string };

const CUSTODY: Custody[] = [
	{
		icon: ServerOffIcon,
		title: "Never through our servers",
		body: "Filings move from the court's site straight to your machine. Hudson never receives, stores, or reads a document — by construction, not by policy.",
	},
	{
		icon: EyeIcon,
		title: "Preview stays local",
		body: "The side-panel preview renders the court's own copy, fetched with your own court session, entirely in your browser. Hudson is never contacted to show you a PDF.",
	},
	{
		icon: FileTextIcon,
		title: "Clean, consistent names",
		body: "The court's opaque filenames become yours — case number, date, document type — applied from your naming rules on every download, including Download all.",
	},
	{
		icon: KeyRoundIcon,
		title: "Sign-in you can revoke",
		body: "The extension signs in with OAuth against your Hudson account — consented, scoped to EDMSpro alone, and revocable at any time. Signing out revokes its tokens.",
	},
	{
		icon: ShieldCheckIcon,
		title: "Least privilege, on purpose",
		body: "The extension runs only on the court's own sites, with the minimum Chrome permissions it can ask for. It has no access to the rest of your browsing.",
	},
	{
		icon: CloudUploadIcon,
		title: "Cloud save is next",
		body: "One-click saves to your own OneDrive are in the works, held to the same rule: documents move browser-to-cloud over a pre-authorized upload — never through Hudson.",
	},
];

function Custody() {
	return (
		<ProductSection
			id="custody"
			tone="layer"
			label="Custody"
			title="Your filings never pass through our servers."
			intro="A tool that touches client documents has to answer one question before any other: where do the documents go? Here, they go from the court to you, and nowhere else."
		>
			<div className="mt-14 grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
				{CUSTODY.map((c) => {
					const Icon = c.icon;
					return (
						<div key={c.title} className="bg-card p-8">
							<Icon className="size-5" strokeWidth={1.5} aria-hidden />
							<h3 className="mt-6 font-semibold text-[15px]">{c.title}</h3>
							<p className="mt-2 text-[13.5px] text-muted-foreground leading-relaxed">
								{c.body}
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
		audience: "New matter intake",
		title: "Take the whole docket in one pass.",
		body: "Download all pulls every filing on the case at once, each one already named the way the file it is going into expects.",
	},
	{
		audience: "Trial prep",
		title: "Find the order without opening four PDFs.",
		body: "Preview beside the docket means you can tell the scheduling order from the amended one before anything lands on your disk.",
	},
	{
		audience: "Firm-wide files",
		title: "One naming convention, everyone.",
		body: "Naming rules live in the account, not in each person's habits, so a filing saved by anyone at the firm arrives named the same way.",
	},
	{
		audience: "Confidential matters",
		title: "Documents that stay between you and the court.",
		body: "Nothing routes through Hudson: the extension uses your own court session, and the file goes straight from the court's site to your machine.",
	},
];

function UseCases() {
	return (
		<ProductSection
			id="use-cases"
			tone="dark"
			label="Use cases"
			title="Where it earns its place."
		>
			<UseCaseGrid items={USE_CASES} tone="dark" />
		</ProductSection>
	);
}

// ---------------------------------------------------------------------------
// Pricing
// ---------------------------------------------------------------------------

function Pricing() {
	return (
		<ProductSection
			id="pricing"
			label="Pricing"
			title="Included with your plan."
		>
			<PlanBand included="Hudson EDMSpro is not sold separately: it comes with Solo and Firm, alongside the research product. Early access is granted per account while the Chrome Web Store listing is in review." />
		</ProductSection>
	);
}
