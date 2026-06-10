import { redirect } from "next/navigation";

// There is no standalone privacy policy — privacy and data practices are
// Section 8 of the Terms of Service (app/terms/page.tsx). This alias exists
// so /privacy (linked from footers, emails, habit) lands somewhere sensible.
// Listed in AuthGate's PUBLIC_PATHS alongside /terms.
export default function PrivacyPage() {
	redirect("/terms#privacy");
}
