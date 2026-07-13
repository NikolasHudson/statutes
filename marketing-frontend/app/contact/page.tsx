// Dedicated contact page — /contact, linked from the footer (deliberately not
// the nav: the nav sells, the footer routes). One focused screen: what to
// write us about on the left, the form on the right, same Carbon register as
// the consulting page's contact band (whose #contact anchor stays for
// consulting-specific CTAs).

import { MailIcon } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import {
	CarbonPage,
	Eyebrow,
	INK,
	PageHero,
	SectionHead,
} from "@/components/marketing/carbon";
import {
	CONSULTING_HREF,
	EMAIL_PRODUCT_HREF,
	PRODUCTS_INDEX_HREF,
} from "@/components/marketing/chrome";
import { ConsultForm } from "@/components/marketing/consult-form";
import { CONTACT_EMAIL } from "@/lib/site";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
	title: "Contact — Hudson Legal Technologies",
	description:
		"Get in touch about Hudson Corpus, the email-assistant pilot, consulting engagements, or anything else. We read everything and reply like people.",
};

const REASONS: { title: string; body: React.ReactNode }[] = [
	{
		title: "Products & beta access",
		body: (
			<>
				Questions about{" "}
				<Link
					href={PRODUCTS_INDEX_HREF}
					className="text-[#0f62fe] hover:underline"
				>
					Hudson Corpus, MCP, or the email assistant
				</Link>{" "}
				— or your firm's beta access.
			</>
		),
	},
	{
		title: "Email-assistant pilot",
		body: (
			<>
				The{" "}
				<Link
					href={EMAIL_PRODUCT_HREF}
					className="text-[#0f62fe] hover:underline"
				>
					assistant that answers your email
				</Link>{" "}
				is in limited pilot — access is granted per address. Tell us about your
				practice and we'll set your addresses up.
			</>
		),
	},
	{
		title: "Consulting",
		body: (
			<>
				Strategy, custom software, data, and applied AI —{" "}
				<Link href={CONSULTING_HREF} className="text-[#0f62fe] hover:underline">
					how we work
				</Link>
				. A sentence about the problem is plenty to start.
			</>
		),
	},
	{
		title: "Everything else",
		body: "Press, partnerships, corpus corrections, or something we haven't thought of. If a citation looks wrong, we especially want to hear it.",
	},
];

export default function ContactPage() {
	return (
		<CarbonPage>
			<PageHero
				eyebrow="Hudson Legal Technologies"
				title="Get in touch."
				lede="Write to us about the products, the pilot, or a project. A human reads everything and replies honestly — usually within a business day."
			/>

			<section className="bg-background">
				<div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
					<SectionHead n="01" label="Contact" title="What can we help with?" />

					<div className="mt-14 grid gap-14 lg:grid-cols-[1fr_1.1fr] lg:gap-20">
						{/* Left — reasons + direct email */}
						<div>
							<div className="grid gap-px border border-border bg-border">
								{REASONS.map((r) => (
									<div key={r.title} className="bg-card p-6">
										<h3 className="font-semibold text-[15px]">{r.title}</h3>
										<p className="mt-2 text-[13.5px] text-muted-foreground leading-relaxed">
											{r.body}
										</p>
									</div>
								))}
							</div>

							<div className="mt-10 border-border border-t pt-6">
								<Eyebrow>Prefer email?</Eyebrow>
								<a
									href={`mailto:${CONTACT_EMAIL}`}
									className="mt-3 inline-flex items-center gap-2 font-medium text-[#0f62fe] text-sm hover:underline"
								>
									<MailIcon className="size-4" />
									{CONTACT_EMAIL}
								</a>
							</div>
						</div>

						{/* Right — the form */}
						<ConsultForm
							submitLabel="Submit message"
							caption="We read everything — replies usually within a business day."
						/>
					</div>
				</div>
			</section>

			<section className={cn("text-white", INK)}>
				<div className="mx-auto max-w-7xl px-5 py-14 sm:px-8">
					<p className="max-w-2xl text-[#c6c6c6] text-[15px] leading-relaxed">
						Hudson Legal Technologies is built in Iowa, for the practice of law.
						If you'd rather see the product than talk about it —{" "}
						<Link
							href={PRODUCTS_INDEX_HREF}
							className="text-[#78a9ff] hover:underline"
						>
							start with the products
						</Link>
						.
					</p>
				</div>
			</section>
		</CarbonPage>
	);
}
