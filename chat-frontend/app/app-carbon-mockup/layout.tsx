import type { Metadata } from "next";
import { CarbonRoot } from "./carbon";

export const metadata: Metadata = {
	title: "Carbon app mockups — Hudson",
	description:
		"IBM Carbon design exploration of the full Hudson Corpus app. Static mockups, not the live app.",
};

// Every screen in the suite shares one CarbonRoot so the theme toggle carries
// across client navigations.
export default function AppCarbonMockupLayout({
	children,
}: {
	children: React.ReactNode;
}) {
	return <CarbonRoot>{children}</CarbonRoot>;
}
