"use client";

// Carbon UI-shell-style header for the marketing site (client: mobile-menu
// state + active-route highlight). Spec: 48px gray-100 (#161616) bar, 14px
// items as full-height hit targets hovering to #292929, bold-prefix wordmark,
// a full-height Blue-60 CTA at the trailing edge, and a 3px blue bottom border
// on the current page's item (Carbon's "current" treatment).

import { ArrowRightIcon, MenuIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { GET_STARTED_URL, SIGN_IN_URL } from "@/lib/site";
import { cn } from "@/lib/utils";
import {
	ABOUT_HREF,
	ARTICLES_HREF,
	CONSULTING_HREF,
	MARKETING_HOME,
	PRICING_HREF,
	PRODUCTS_INDEX_HREF,
} from "./chrome";

const NAV_LINKS = [
	{ label: "Products", href: PRODUCTS_INDEX_HREF },
	{ label: "Consulting", href: CONSULTING_HREF },
	{ label: "Articles", href: ARTICLES_HREF },
	{ label: "Pricing", href: PRICING_HREF },
	{ label: "About", href: ABOUT_HREF },
];

// Carbon header-name treatment: bold prefix, regular product name.
export function CarbonWordmark() {
	return (
		<Link
			href={MARKETING_HOME}
			className="flex items-baseline gap-1.5 whitespace-nowrap text-sm"
		>
			<span className="font-semibold tracking-wide">Hudson</span>
			<span className="hidden text-[#c6c6c6] sm:inline">
				Legal Technologies
			</span>
		</Link>
	);
}

export function CarbonNav() {
	const [menuOpen, setMenuOpen] = useState(false);
	const pathname = usePathname();

	const isCurrent = (href: string) =>
		pathname === href || pathname.startsWith(`${href}/`);

	return (
		<header className="sticky top-0 z-50 border-[#393939] border-b bg-[#161616] text-white">
			<div className="mx-auto flex h-12 max-w-7xl items-stretch px-5 sm:px-8">
				<div className="flex items-center pr-6">
					<CarbonWordmark />
				</div>

				<nav className="hidden items-stretch md:flex">
					{NAV_LINKS.map((l) => (
						<Link
							key={l.label}
							href={l.href}
							className={cn(
								"flex items-center border-transparent border-b-[3px] px-4 text-sm transition-colors hover:bg-[#292929] hover:text-white",
								isCurrent(l.href)
									? "border-[#0f62fe] text-white"
									: "text-[#c6c6c6]",
							)}
						>
							{l.label}
						</Link>
					))}
				</nav>

				<div className="ms-auto hidden items-stretch md:flex">
					<a
						href={SIGN_IN_URL}
						className="flex items-center px-4 text-[#c6c6c6] text-sm transition-colors hover:bg-[#292929] hover:text-white"
					>
						Sign in
					</a>
					<a
						href={GET_STARTED_URL}
						className="flex items-center gap-6 bg-[#0f62fe] px-4 text-sm text-white transition-colors hover:bg-[#0353e9]"
					>
						Get started
						<ArrowRightIcon className="size-4" />
					</a>
				</div>

				<button
					type="button"
					onClick={() => setMenuOpen(!menuOpen)}
					className="ms-auto flex w-12 items-center justify-center text-white transition-colors hover:bg-[#292929] md:hidden"
					aria-label="Toggle menu"
				>
					{menuOpen ? (
						<XIcon className="size-5" />
					) : (
						<MenuIcon className="size-5" />
					)}
				</button>
			</div>

			{menuOpen && (
				<div className="border-[#393939] border-t bg-[#161616] md:hidden">
					<nav className="flex flex-col">
						{NAV_LINKS.map((l) => (
							<Link
								key={l.label}
								href={l.href}
								onClick={() => setMenuOpen(false)}
								className={cn(
									"border-[#292929] border-b px-5 py-3.5 text-sm transition-colors hover:bg-[#292929] hover:text-white",
									isCurrent(l.href) ? "text-white" : "text-[#c6c6c6]",
								)}
							>
								{l.label}
							</Link>
						))}
						<a
							href={SIGN_IN_URL}
							className="border-[#292929] border-b px-5 py-3.5 text-[#c6c6c6] text-sm transition-colors hover:bg-[#292929] hover:text-white"
						>
							Sign in
						</a>
						<a
							href={GET_STARTED_URL}
							className="flex items-center justify-between bg-[#0f62fe] px-5 py-3.5 text-sm text-white transition-colors hover:bg-[#0353e9]"
						>
							Get started
							<ArrowRightIcon className="size-4" />
						</a>
					</nav>
				</div>
			)}
		</header>
	);
}
