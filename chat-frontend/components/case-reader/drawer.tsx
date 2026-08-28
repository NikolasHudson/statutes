"use client";

// A Carbon-styled side panel for the reader's off-canvas surfaces (outline /
// citator / ask / display below the widths where their rails show). Kept
// local instead of the shadcn Sheet so it lives on the Carbon tokens.

import { XIcon } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

export function Drawer({
	open,
	title,
	onClose,
	children,
	className,
}: {
	open: boolean;
	title: string;
	onClose: () => void;
	children: ReactNode;
	className?: string;
}) {
	const panelRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (!open) return;
		const onKey = (e: KeyboardEvent) => {
			if (e.key === "Escape") onClose();
		};
		document.addEventListener("keydown", onKey);
		// Focus the panel so Escape works and screen readers land inside.
		panelRef.current?.focus();
		return () => document.removeEventListener("keydown", onKey);
	}, [open, onClose]);

	if (!open) return null;
	return (
		<div className="fixed inset-0 z-40 print:hidden">
			<button
				type="button"
				aria-label="Close panel"
				onClick={onClose}
				className="absolute inset-0 bg-black/40"
			/>
			<div
				ref={panelRef}
				role="dialog"
				aria-modal="true"
				aria-label={title}
				tabIndex={-1}
				className={cn(
					"absolute inset-y-0 right-0 flex w-full flex-col bg-[var(--cds-bg)] text-[var(--cds-text)] shadow-[-4px_0_16px_rgba(0,0,0,0.28)] outline-none sm:max-w-md",
					className,
				)}
			>
				<div className="flex h-12 shrink-0 items-center justify-between border-[var(--cds-border)] border-b pr-1 pl-4">
					<span className="font-mono text-[11px] text-[var(--cds-helper)] uppercase tracking-[0.18em]">
						{title}
					</span>
					<button
						type="button"
						aria-label="Close"
						onClick={onClose}
						className="flex size-10 items-center justify-center text-[var(--cds-text-2)] transition-colors hover:bg-[var(--cds-layer-hover)]"
					>
						<XIcon className="size-4" />
					</button>
				</div>
				<div className="flex min-h-0 flex-1 flex-col">{children}</div>
			</div>
		</div>
	);
}
