// Markdown renderer for marketing articles. Articles are authored as .md
// (backend/content/articles/) or in the Django admin, and arrive here as a
// GFM string; this maps markdown elements onto the site's hand-styled prose
// so DB-driven articles read identically to the original hand-built one.
//
// Conventions:
//   - the first paragraph gets the drop cap (pure CSS, no counting);
//   - a plain blockquote renders as a pullquote;
//   - a blockquote whose first line is **bold** renders as a callout box
//     with that bold line as its title.

import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";

export function ArticleBody({ markdown }: { markdown: string }) {
	return (
		<div className="pt-10 lg:pt-14 [&>p:first-of-type]:first-letter:float-left [&>p:first-of-type]:first-letter:mr-2 [&>p:first-of-type]:first-letter:font-light [&>p:first-of-type]:first-letter:text-6xl [&>p:first-of-type]:first-letter:text-[#0f62fe] [&>p:first-of-type]:first-letter:leading-[0.8]">
			<ReactMarkdown
				remarkPlugins={[remarkGfm]}
				rehypePlugins={[rehypeSlug]}
				components={{
					p: (props) => (
						<p
							className="mt-5 text-[17px] text-foreground/85 leading-[1.75]"
							{...props}
						/>
					),
					h2: (props) => (
						<h2
							className="mt-12 scroll-mt-24 font-semibold text-2xl"
							{...props}
						/>
					),
					h3: (props) => (
						<h3
							className="mt-10 scroll-mt-24 font-semibold text-xl"
							{...props}
						/>
					),
					a: (props) => (
						<a className="text-[#0f62fe] hover:underline" {...props} />
					),
					ul: (props) => (
						<ul
							className="mt-5 list-disc space-y-2 pl-6 text-[17px] text-foreground/85 leading-[1.75]"
							{...props}
						/>
					),
					ol: (props) => (
						<ol
							className="mt-5 list-decimal space-y-2 pl-6 text-[17px] text-foreground/85 leading-[1.75]"
							{...props}
						/>
					),
					code: (props) => (
						<code
							className="border border-border bg-card px-1.5 py-px font-mono text-[14px]"
							{...props}
						/>
					),
					hr: () => <hr className="my-10 border-border" />,
					blockquote: Blockquote,
				}}
			>
				{markdown}
			</ReactMarkdown>
		</div>
	);
}

// hast shim — just enough of the tree to spot a bold first line.
type HastNode = {
	type?: string;
	tagName?: string;
	children?: HastNode[];
};

function hasBoldLead(node?: HastNode): boolean {
	const firstBlock = node?.children?.find((c) => c.type === "element");
	if (firstBlock?.tagName !== "p") return false;
	return firstBlock.children?.[0]?.tagName === "strong";
}

function Blockquote({
	node,
	...props
}: ComponentProps<"blockquote"> & { node?: HastNode }) {
	if (hasBoldLead(node)) {
		// Callout: bordered card, Blue-60 spine, bold title line then body.
		return (
			<blockquote
				className="my-8 border border-border border-l-2 border-l-[#0f62fe] bg-card p-5 [&_p]:mt-3 [&_p]:text-[15px] [&_p]:text-muted-foreground [&_p]:leading-relaxed [&_p:first-of-type]:mt-0 [&_strong]:mb-2 [&_strong]:block [&_strong]:font-semibold [&_strong]:text-[15px] [&_strong]:text-foreground"
				{...props}
			/>
		);
	}
	// Pullquote: Blue-60 spine, big light type.
	return (
		<blockquote
			className="my-10 border-[#0f62fe] border-l-2 pl-6 [&_p]:mt-0 [&_p]:font-light [&_p]:text-2xl [&_p]:text-foreground [&_p]:leading-snug"
			{...props}
		/>
	);
}
