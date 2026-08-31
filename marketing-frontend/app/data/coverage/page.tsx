// /data/coverage has no index page yet — Iowa is the first unit in the
// series. Redirect (temporary, not permanent) so the URL works today and can
// become a real index when a second unit publishes.

import { redirect } from "next/navigation";
import { COVERAGE_IOWA_HREF } from "@/components/marketing/chrome";

export default function CoverageIndexPage() {
	redirect(COVERAGE_IOWA_HREF);
}
