// Side-nav preference: whether the signed-in user keeps the full nav docked
// (256px, in flow) or lives on the 48px icon rail with the hover flyout. See
// SIDEBAR_PLAN.md.
//
// Scoped per user id, same discipline as lib/thread-store.ts: it's not
// sensitive, but a shared key on a firm machine would let one person's pin
// silently reset another's. Nothing here needs clearing at sign-out.

const KEY_PREFIX = "hudson:nav:docked";

const storeKey = (userId: number) => `${KEY_PREFIX}:${userId}`;

/** `true`/`false` if the user has ever pinned or unpinned; `null` if unset. */
export function loadDocked(userId: number): boolean | null {
	try {
		const raw = localStorage.getItem(storeKey(userId));
		if (raw === "1") return true;
		if (raw === "0") return false;
		return null;
	} catch {
		return null;
	}
}

export function saveDocked(userId: number, docked: boolean) {
	try {
		localStorage.setItem(storeKey(userId), docked ? "1" : "0");
	} catch {
		/* storage unavailable — the pin just won't survive a reload */
	}
}
