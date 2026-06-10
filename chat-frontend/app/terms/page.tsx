import type { Metadata } from "next";
import Link from "next/link";

// Terms of Service — the full text behind the onboarding Terms step and the
// links on the sign-in screen. This is a public, static server component
// (AuthGate exempts /terms) so the terms are readable before acceptance.
//
// IMPORTANT: the version/effective date here must stay in sync with
// CURRENT_TOS_VERSION in backend/apps/api/accounts.py. Bumping the backend
// constant is what forces re-acceptance; updating this page is what users
// actually re-read. Change them together.

const TOS_VERSION = "2026-06-10";
const EFFECTIVE_DATE = "June 10, 2026";

export const metadata: Metadata = {
	title: "Terms of Service — Iowa Legal Corpus",
	description:
		"Terms of Service and data practices for the Iowa Legal Corpus research service.",
};

const SECTIONS: { id: string; title: string }[] = [
	{ id: "acceptance", title: "1. Acceptance of these Terms" },
	{ id: "service", title: "2. The Service" },
	{ id: "not-legal-advice", title: "3. Not Legal Advice" },
	{ id: "accounts", title: "4. Eligibility, Accounts & API Keys" },
	{ id: "acceptable-use", title: "5. Acceptable Use" },
	{ id: "ai-outputs", title: "6. AI-Generated Output & Accuracy" },
	{ id: "ip", title: "7. Intellectual Property" },
	{ id: "privacy", title: "8. Privacy & Your Data" },
	{ id: "third-parties", title: "9. Third-Party Services" },
	{ id: "fees", title: "10. Fees" },
	{ id: "termination", title: "11. Suspension & Termination" },
	{ id: "warranties", title: "12. Disclaimer of Warranties" },
	{ id: "liability", title: "13. Limitation of Liability" },
	{ id: "indemnification", title: "14. Indemnification" },
	{ id: "changes", title: "15. Changes to these Terms" },
	{ id: "law", title: "16. Governing Law" },
	{ id: "contact", title: "17. Contact" },
];

function Section({
	id,
	title,
	children,
}: {
	id: string;
	title: string;
	children: React.ReactNode;
}) {
	return (
		<section id={id} className="scroll-mt-24">
			<h2 className="mt-10 mb-3 font-semibold text-foreground text-lg">
				{title}
			</h2>
			<div className="space-y-3 text-[15px] text-muted-foreground leading-relaxed">
				{children}
			</div>
		</section>
	);
}

export default function TermsPage() {
	return (
		<main className="min-h-dvh bg-background">
			<div className="mx-auto max-w-3xl px-6 py-12">
				<p className="text-muted-foreground text-sm">
					<Link href="/" className="text-primary underline underline-offset-2">
						← Back to the app
					</Link>
				</p>

				<h1 className="mt-6 font-semibold text-3xl text-foreground tracking-tight">
					Terms of Service
				</h1>
				<p className="mt-2 text-muted-foreground text-sm">
					Version {TOS_VERSION} · Effective {EFFECTIVE_DATE}
				</p>

				<div className="mt-6 rounded-lg border bg-muted/20 p-4 text-[14px] text-muted-foreground leading-relaxed">
					<p className="font-medium text-foreground">Plain-English summary</p>
					<p className="mt-1.5">
						This is a legal research tool, not a lawyer. Its answers — including
						citations, quotations, and &ldquo;good law&rdquo; signals — are
						generated with the help of AI and can be wrong. Verify everything
						against the official source before relying on it. Use the service
						lawfully, don&apos;t bulk-scrape or resell it, and keep your
						credentials to yourself. We store your account details and
						preferences, keep chat logs only briefly, and never sell your data.
						The summary doesn&apos;t replace the terms below.
					</p>
				</div>

				<nav className="mt-8 rounded-lg border p-4">
					<p className="mb-2 font-medium text-foreground text-sm">Contents</p>
					<ol className="grid gap-1 text-sm sm:grid-cols-2">
						{SECTIONS.map((s) => (
							<li key={s.id}>
								<a
									href={`#${s.id}`}
									className="text-muted-foreground hover:text-primary hover:underline underline-offset-2"
								>
									{s.title}
								</a>
							</li>
						))}
					</ol>
				</nav>

				<Section id="acceptance" title="1. Acceptance of these Terms">
					<p>
						These Terms of Service (the &ldquo;Terms&rdquo;) are an agreement
						between you and Hudson Legal Tech (&ldquo;we,&rdquo;
						&ldquo;us&rdquo;), the operator of the Iowa Legal Corpus research
						service available at corpus.nick.law, including its web application,
						APIs, and MCP server (together, the &ldquo;Service&rdquo;). By
						creating an account, accepting the Terms during onboarding, or using
						the Service, you agree to be bound by them. If you are using the
						Service on behalf of a firm or other organization, you represent
						that you have authority to bind it, and &ldquo;you&rdquo; includes
						that organization.
					</p>
					<p>If you do not agree to these Terms, do not use the Service.</p>
				</Section>

				<Section id="service" title="2. The Service">
					<p>
						The Service provides research tools over a corpus of primary legal
						materials — statutes, administrative rules, court rules, and
						judicial opinions, currently centered on Iowa law — including
						full-text and semantic search, browsing, citation lookup, an
						AI-assisted research chat, document verification, and related
						features. Coverage, currency, and features vary over time and are
						not guaranteed; the corpus may lag the official sources, and some
						materials (for example, very recent amendments or opinions) may be
						missing or superseded.
					</p>
					<p>
						The official versions of the law are those published by the issuing
						government bodies. Where the Service and an official source
						disagree, the official source controls.
					</p>
				</Section>

				<Section id="not-legal-advice" title="3. Not Legal Advice">
					<p className="font-medium text-foreground">
						The Service provides legal research assistance, not legal advice.
					</p>
					<p>
						No output of the Service — search results, chat answers, citations,
						treatment or &ldquo;good law&rdquo; indicators, summaries, or
						document analyses — constitutes legal advice, and your use of the
						Service does not create an attorney–client relationship with us or
						anyone else. We are not a law firm. If you need legal advice,
						consult a licensed attorney. If you are an attorney, you remain
						solely responsible for your own professional obligations, including
						the duty of competence and the duty to verify the authorities you
						cite.
					</p>
				</Section>

				<Section id="accounts" title="4. Eligibility, Accounts & API Keys">
					<p>
						You must be at least 18 years old to use the Service. You agree to
						provide accurate registration information and to keep it current.
						You are responsible for all activity under your account and for
						keeping your password and any API keys confidential. API keys grant
						programmatic access to the Service (including via MCP clients);
						treat them like passwords, do not embed them in public code or
						client-side applications, and revoke any key you believe is
						compromised. Notify us promptly of any unauthorized use of your
						account.
					</p>
				</Section>

				<Section id="acceptable-use" title="5. Acceptable Use">
					<p>
						You agree to use the Service only for lawful research purposes. You
						will not:
					</p>
					<ul className="list-disc space-y-1.5 pl-5">
						<li>
							scrape, crawl, bulk-download, or systematically extract the
							corpus, or resell, redistribute, or republish substantial portions
							of it as a competing dataset or service;
						</li>
						<li>
							circumvent or attempt to circumvent authentication, rate limits,
							usage quotas, or other technical restrictions;
						</li>
						<li>
							probe, scan, or test the vulnerability of the Service except
							pursuant to a written authorization from us;
						</li>
						<li>
							use the Service to violate any law, court order, or the rights of
							others, or to harass, defraud, or mislead;
						</li>
						<li>
							share one account or API key across multiple people or
							organizations, or misrepresent your identity to us;
						</li>
						<li>
							use outputs to train a competing legal research model or service.
						</li>
					</ul>
					<p>
						The Service enforces fair-use limits (for example, daily and monthly
						chat quotas). We may adjust these limits to protect the Service.
					</p>
				</Section>

				<Section id="ai-outputs" title="6. AI-Generated Output & Accuracy">
					<p>
						Parts of the Service generate output using large language models and
						machine-learning retrieval. AI output can be incomplete, outdated,
						or simply wrong — including in ways that look authoritative, such as
						fabricated or mis-attributed citations, inaccurate quotations, or
						incorrect statements about whether an authority is still good law.
						Automated verification steps in the Service (such as citation and
						quote checking, or treatment flags) reduce but do not eliminate
						these errors and are provided on a best-effort basis only.
					</p>
					<p className="font-medium text-foreground">
						You are responsible for independently verifying every authority,
						quotation, and proposition against the official source before
						relying on it or citing it in any filing or advice.
					</p>
				</Section>

				<Section id="ip" title="7. Intellectual Property">
					<p>
						Primary legal materials — statutes, rules, regulations, and judicial
						opinions — are edicts of government and are not subject to
						copyright. These Terms do not restrict your use of the underlying
						law obtained from official sources.
					</p>
					<p>
						The Service itself — its software, design, search and retrieval
						systems, editorial enhancements, structure, compilation, and
						metadata — is owned by us or our licensors and is protected by
						applicable intellectual-property laws. We grant you a limited,
						non-exclusive, non-transferable, revocable license to access and use
						the Service for your own research in accordance with these Terms. We
						claim no ownership of the queries and documents you submit; you
						grant us a limited license to process them as needed to operate the
						Service as described in Section 8.
					</p>
				</Section>

				<Section id="privacy" title="8. Privacy & Your Data">
					<p>
						We collect and store what we need to operate the Service: your
						account details (name, email, professional profile, and address if
						you provide them), your preferences and settings, your acceptance of
						these Terms, API-key metadata, and security and audit logs (such as
						login events and approximate IP addresses) kept for abuse prevention
						and account protection.
					</p>
					<p>
						Research chat questions and answers are logged as traces for quality
						and abuse monitoring and are automatically deleted on a short
						retention cycle — currently seven days. Documents you submit for
						verification are processed to provide the feature and are not used
						to build a public dataset. We do not sell your personal data, and we
						do not use your queries or documents to train our own or third-party
						foundation models.
					</p>
					<p>
						To provide AI features, your queries and relevant excerpts are sent
						to the third-party processors described in Section 9. Data is stored
						with our hosting provider in the United States. You may request a
						copy or deletion of your account data by contacting us (Section 17);
						we will action deletion requests within 30 days, except for records
						we must keep for security, legal, or accounting reasons.
					</p>
				</Section>

				<Section id="third-parties" title="9. Third-Party Services">
					<p>
						The Service is built on third-party infrastructure and AI providers,
						currently including DigitalOcean (hosting and storage), OpenAI
						(language-model responses), and Voyage AI (embeddings and
						reranking). Your queries and the document excerpts needed to answer
						them are transmitted to the AI providers under agreements that
						restrict their use of that data. We may change providers; material
						changes to how your data is processed will be reflected in an
						updated version of these Terms.
					</p>
				</Section>

				<Section id="fees" title="10. Fees">
					<p>
						The Service is currently offered without charge, subject to fair-use
						limits. We may introduce paid plans or change limits in the future;
						we will give reasonable advance notice before any feature you use
						becomes paid, and you will never be charged without affirmatively
						signing up for a paid plan.
					</p>
				</Section>

				<Section id="termination" title="11. Suspension & Termination">
					<p>
						You may stop using the Service and request account deletion at any
						time. We may suspend or terminate your access (or any API key) if
						you materially breach these Terms, if your use threatens the
						security or integrity of the Service, or if we are required to by
						law — with notice where practicable. We may also discontinue the
						Service or any feature; if we discontinue the Service entirely, we
						will make reasonable efforts to give advance notice. Sections 3, 6,
						7, and 12–16 survive termination.
					</p>
				</Section>

				<Section id="warranties" title="12. Disclaimer of Warranties">
					<p>
						THE SERVICE IS PROVIDED &ldquo;AS IS&rdquo; AND &ldquo;AS
						AVAILABLE,&rdquo; WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR
						IMPLIED, INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
						PARTICULAR PURPOSE, NON-INFRINGEMENT, ACCURACY, COMPLETENESS,
						CURRENCY, OR UNINTERRUPTED AVAILABILITY. WITHOUT LIMITING THE
						FOREGOING, WE DO NOT WARRANT THAT THE CORPUS IS COMPLETE OR CURRENT,
						THAT SEARCH RESULTS ARE EXHAUSTIVE, OR THAT ANY OUTPUT (INCLUDING
						CITATIONS AND GOOD-LAW SIGNALS) IS ACCURATE.
					</p>
				</Section>

				<Section id="liability" title="13. Limitation of Liability">
					<p>
						TO THE MAXIMUM EXTENT PERMITTED BY LAW, WE WILL NOT BE LIABLE FOR
						ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE
						DAMAGES, OR FOR LOST PROFITS, LOST DATA, PROFESSIONAL SANCTIONS, OR
						ADVERSE LEGAL OUTCOMES, ARISING OUT OF OR RELATING TO YOUR USE OF
						THE SERVICE OR RELIANCE ON ITS OUTPUT, EVEN IF ADVISED OF THE
						POSSIBILITY. OUR TOTAL AGGREGATE LIABILITY FOR ALL CLAIMS RELATING
						TO THE SERVICE WILL NOT EXCEED THE GREATER OF THE AMOUNTS YOU PAID
						US FOR THE SERVICE IN THE TWELVE MONTHS BEFORE THE CLAIM AROSE OR
						ONE HUNDRED U.S. DOLLARS (US$100). SOME JURISDICTIONS DO NOT ALLOW
						CERTAIN LIMITATIONS, SO SOME OF THE ABOVE MAY NOT APPLY TO YOU.
					</p>
				</Section>

				<Section id="indemnification" title="14. Indemnification">
					<p>
						You will indemnify and hold us harmless from claims, damages, and
						reasonable costs (including attorneys&apos; fees) arising from your
						violation of these Terms or your misuse of the Service, except to
						the extent caused by our own breach of these Terms.
					</p>
				</Section>

				<Section id="changes" title="15. Changes to these Terms">
					<p>
						We may update these Terms from time to time. Each version is
						identified by the version string at the top of this page. For
						material changes we will require re-acceptance in the application
						before continued use. Your acceptance of a given version is recorded
						with your account. Continued use of the Service after a new version
						takes effect constitutes acceptance of it.
					</p>
				</Section>

				<Section id="law" title="16. Governing Law">
					<p>
						These Terms are governed by the laws of the State of Iowa, without
						regard to conflict-of-laws rules. The state and federal courts
						located in Iowa will have exclusive jurisdiction over any dispute
						arising out of these Terms or the Service, and each party consents
						to personal jurisdiction and venue there. Before filing any claim,
						you agree to contact us and attempt in good faith to resolve the
						dispute informally for 30 days.
					</p>
				</Section>

				<Section id="contact" title="17. Contact">
					<p>
						Questions about these Terms, privacy, or data requests:{" "}
						<a
							href="mailto:nick@nickhudson.me"
							className="text-primary underline underline-offset-2"
						>
							nick@nickhudson.me
						</a>
						.
					</p>
				</Section>

				<p className="mt-12 border-t pt-6 text-muted-foreground text-xs">
					© {new Date().getFullYear()} Hudson Legal Tech · Iowa Legal Corpus ·
					Version {TOS_VERSION}
				</p>
			</div>
		</main>
	);
}
