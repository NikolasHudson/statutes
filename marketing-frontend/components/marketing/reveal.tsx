"use client";

// Scroll-reveal wrapper: stamps `data-shown` on itself the first time it
// enters the viewport, so children animate in with pure CSS via
// `group-data-[shown]/rv:*` variants (see SectionHead in carbon.tsx). Fires
// once — sections don't re-animate on scroll-back. Users with reduced motion
// (and any environment without IntersectionObserver) get the shown state
// immediately; the children also carry motion-reduce overrides so nothing
// moves for them either way.

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export function Reveal({
	children,
	className,
}: {
	children: React.ReactNode;
	className?: string;
}) {
	const ref = useRef<HTMLDivElement>(null);
	const [shown, setShown] = useState(false);

	useEffect(() => {
		const el = ref.current;
		if (!el) return;
		if (
			typeof IntersectionObserver === "undefined" ||
			window.matchMedia("(prefers-reduced-motion: reduce)").matches
		) {
			setShown(true);
			return;
		}
		const io = new IntersectionObserver(
			([entry]) => {
				if (entry.isIntersecting) {
					setShown(true);
					io.disconnect();
				}
			},
			{ threshold: 0.2, rootMargin: "0px 0px -60px 0px" },
		);
		io.observe(el);
		return () => io.disconnect();
	}, []);

	return (
		<div
			ref={ref}
			data-shown={shown || undefined}
			className={cn("group/rv", className)}
		>
			{children}
		</div>
	);
}
