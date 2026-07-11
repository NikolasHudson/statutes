"use client";

// Admin · Articles · Edit — manage one marketing-site article. Fetches the
// full row (drafts included) and hands it to the shared editor.

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
	BtnGhost,
	Eyebrow,
	Notification,
} from "@/components/carbon/primitives";
import { AccountError } from "@/lib/iowa-account";
import { type AdminArticleDetail, getAdminArticle } from "@/lib/iowa-admin";
import { ArticleEditor } from "../editor";

export default function EditArticlePage() {
	const params = useParams<{ id: string }>();
	const id = Number(params.id);
	const [article, setArticle] = useState<AdminArticleDetail | null>(null);
	const [error, setError] = useState<Error | null>(null);

	useEffect(() => {
		if (!Number.isFinite(id)) {
			setError(new Error("bad article id"));
			return;
		}
		let cancelled = false;
		getAdminArticle(id)
			.then((a) => !cancelled && setArticle(a))
			.catch((e) => !cancelled && setError(e as Error));
		return () => {
			cancelled = true;
		};
	}, [id]);

	const httpStatus = error instanceof AccountError ? error.status : null;

	return (
		<div className="mx-auto w-full max-w-[1320px] px-5 py-10 sm:px-8">
			<header>
				<Eyebrow>
					<Link href="/admin/articles" className="hover:underline">
						Admin · Articles
					</Link>{" "}
					· Edit
				</Eyebrow>
				<h1 className="mt-4 max-w-3xl font-light text-3xl sm:text-4xl">
					{article ? article.title : "Edit article"}
				</h1>
			</header>

			{httpStatus === 401 ? (
				<Notification
					kind="error"
					title="Staff only"
					className="mt-10 max-w-xl"
					action={
						<BtnGhost onClick={() => window.location.reload()}>
							Sign in
						</BtnGhost>
					}
				>
					You need an active staff session to view this page.
				</Notification>
			) : httpStatus === 404 ? (
				<Notification
					kind="error"
					title="No such article"
					className="mt-10 max-w-xl"
				>
					This article doesn't exist —{" "}
					<Link href="/admin/articles" className="underline">
						back to the list
					</Link>
					.
				</Notification>
			) : error ? (
				<Notification
					kind="error"
					title="Couldn't load article"
					className="mt-10 max-w-xl"
				>
					{error.message}
				</Notification>
			) : article === null ? (
				<p className="mt-10 text-[var(--cds-text-2)] text-sm">
					Loading article…
				</p>
			) : (
				<ArticleEditor initial={article} />
			)}
		</div>
	);
}
