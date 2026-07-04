import type { Metadata } from "next";
import { CarbonRoot } from "@/components/carbon/primitives";
import { V2Shell } from "./shell";

export const metadata: Metadata = {
	title: "Hudson Corpus",
	description:
		"Grounded, citable interface to the Iowa Code, Court Rules, and case law.",
};

// Functional Carbon rebuild of the app. /v2 is NOT a public path (see
// auth-gate.tsx), so this layout only renders signed-in: AuthGate shows the
// Carbon sign-in screen instead while signed out. One CarbonRoot wraps the
// whole group so the theme toggle carries across client navigations.
export default function V2Layout({ children }: { children: React.ReactNode }) {
	return (
		<CarbonRoot>
			<V2Shell>{children}</V2Shell>
		</CarbonRoot>
	);
}
