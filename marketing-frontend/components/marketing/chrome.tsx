// Route constants shared across the marketing site. The Carbon chrome
// (nav, footer, page shell) lives in carbon.tsx / carbon-nav.tsx; internal
// links use these real routes, while links INTO the app (Sign in /
// Get started) point at the app origin via lib/site — it's a separate
// deployment, so those are cross-origin hard navigations by design.
//
// The legacy Geist/navy chrome (SiteNav, SiteFooter, navyBackdrop) lived here
// until the Carbon home was promoted to "/" on 2026-07-10.

export const MARKETING_HOME = "/";
export const ARTICLES_HREF = "/articles";
export const PRODUCTS_INDEX_HREF = "/products";
export const PRODUCT_HREF = "/products/corpus";
export const MCP_PRODUCT_HREF = "/products/mcp";
export const EMAIL_PRODUCT_HREF = "/products/email";
export const EDMS_PRODUCT_HREF = "/products/edms";
export const CONSULTING_HREF = "/consulting";
export const CONTACT_HREF = "/contact";
export const PRICING_HREF = "/pricing";
export const ABOUT_HREF = "/about";
export const DATA_HREF = "/data";
