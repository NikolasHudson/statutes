// Shared display mapping for the admin user pages (list + detail). Lives
// outside page.tsx because Next.js page modules may only export the route
// component and route config.

import type { TagKind } from "@/components/carbon/primitives";
import type { UsageTier } from "@/lib/iowa-admin";

export const TIER_TAGS: Record<UsageTier, { label: string; kind: TagKind }> = {
	free: { label: "Trial", kind: "gray" },
	solo: { label: "Solo", kind: "blue" },
	firm: { label: "Firm", kind: "purple" },
	custom: { label: "Custom", kind: "gray" },
};
