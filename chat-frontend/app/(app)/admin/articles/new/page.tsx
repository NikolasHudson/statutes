"use client";

// Admin · Articles · New — create a marketing-site article. On save it
// becomes a DB row (same store the md-file import writes to) and the page
// hands off to the edit view.

import Link from "next/link";
import { Eyebrow } from "@/components/carbon/primitives";
import { ArticleEditor } from "../editor";

export default function NewArticlePage() {
	return (
		<div className="mx-auto w-full max-w-[1320px] px-5 py-10 sm:px-8">
			<header>
				<Eyebrow>
					<Link href="/admin/articles" className="hover:underline">
						Admin · Articles
					</Link>{" "}
					· New
				</Eyebrow>
				<h1 className="mt-4 font-light text-3xl sm:text-4xl">New article</h1>
				<p className="mt-3 max-w-xl text-[15px] text-[var(--cds-text-2)] leading-relaxed">
					Drafts stay hidden until you flip Published. Prefer a markdown file in
					backend/content/articles/ for posts you want reviewed in git.
				</p>
			</header>
			<ArticleEditor />
		</div>
	);
}
