// Shared option lists for the onboarding wizard (app/onboarding) and the
// account settings page (app/account). Values mirror the backend TextChoices in
// apps/accounts/profile.py (Role / SearchScope / CitationStyle / Theme); labels
// are display-only. Jurisdiction & timezone are free text on the server, so
// value === the stored string. Keep this the single source of truth so the two
// surfaces never drift.

export type Option = { value: string; label: string };

export const ROLES: Option[] = [
	{ value: "attorney", label: "Attorney" },
	{ value: "paralegal", label: "Paralegal" },
	{ value: "law_clerk", label: "Law clerk" },
	{ value: "law_student", label: "Law student" },
	{ value: "researcher", label: "Legal researcher" },
	{ value: "other", label: "Other" },
];

export const JURISDICTIONS: Option[] = [
	"Iowa",
	"Federal",
	"All states",
	"California",
	"Illinois",
	"New York",
	"Texas",
].map((j) => ({ value: j, label: j }));

export const TIMEZONES: Option[] = [
	{ value: "America/Chicago", label: "America/Chicago (Central)" },
	{ value: "America/New_York", label: "America/New_York (Eastern)" },
	{ value: "America/Denver", label: "America/Denver (Mountain)" },
	{ value: "America/Los_Angeles", label: "America/Los_Angeles (Pacific)" },
];

export const CITATION_STYLES: Option[] = [
	{ value: "bluebook", label: "Bluebook (21st ed.)" },
	{ value: "alwd", label: "ALWD Guide" },
	{ value: "iowa", label: "Iowa local rules" },
];

export const SEARCH_SCOPES: Option[] = [
	{ value: "all", label: "Everything" },
	{ value: "cases", label: "Case law only" },
	{ value: "statutes", label: "Statutes & codes only" },
	{ value: "secondary", label: "Secondary sources only" },
];

export const THEMES: Option[] = [
	{ value: "light", label: "Light" },
	{ value: "dark", label: "Dark" },
	{ value: "system", label: "System" },
];

export const labelOf = (opts: Option[], value: string) =>
	opts.find((o) => o.value === value)?.label ?? value;
