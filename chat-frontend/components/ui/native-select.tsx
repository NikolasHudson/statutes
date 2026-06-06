"use client";

// A native <select> styled to match the Input primitive — there's no shadcn
// Select primitive in this project, and a native control is the right call for
// short single-choice lists (keyboard + mobile friendly, no portal). Shared by
// the onboarding wizard and the account settings page.

import type { LucideIcon } from "lucide-react";
import type { Option } from "@/lib/settings-options";
import { cn } from "@/lib/utils";

export function NativeSelect({
	value,
	onChange,
	options,
	icon: Icon,
	className,
}: {
	value: string;
	onChange: (v: string) => void;
	options: Option[];
	icon?: LucideIcon;
	className?: string;
}) {
	return (
		<div className={cn("relative", className)}>
			{Icon && (
				<Icon className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-3 size-4 text-muted-foreground" />
			)}
			<select
				value={value}
				onChange={(e) => onChange(e.target.value)}
				className={cn(
					"h-9 w-full appearance-none rounded-md border bg-transparent pr-9 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
					Icon ? "pl-9" : "pl-3",
				)}
			>
				{options.map((o) => (
					<option key={o.value} value={o.value}>
						{o.label}
					</option>
				))}
			</select>
			<svg
				className="-translate-y-1/2 pointer-events-none absolute top-1/2 right-3 size-3.5 text-muted-foreground"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				strokeWidth="2"
				aria-hidden="true"
			>
				<path d="m6 9 6 6 6-6" />
			</svg>
		</div>
	);
}
