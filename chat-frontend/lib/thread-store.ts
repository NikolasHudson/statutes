// Client-side chat-thread persistence, scoped per signed-in user.
//
// Threads live only in localStorage (there is deliberately no server-side
// per-user chat history), so the storage key MUST be namespaced by user id:
// a bare shared key would hand user A's legal-research threads to user B on
// the same browser after an account switch — the exact leak a shared
// firm/library machine invites. For the same reason sign-out wipes every
// thread store on the device (see clearThreadStores, called from the auth
// gate): localStorage outlives the session, and "signed out" on a shared
// computer must mean the next person can't read your chats.

const STORE_PREFIX = "hlt-v2-threads";
// The pre-scoping global key. Never migrated into a user's store — the blob
// can't prove which account wrote it, so adopting it could itself leak
// across users. Dropped on sight instead.
const LEGACY_KEY = STORE_PREFIX;

const storeKey = (userId: number) => `${STORE_PREFIX}:${userId}`;

export function loadThreads<T>(userId: number): T[] {
	try {
		localStorage.removeItem(LEGACY_KEY);
		const raw = localStorage.getItem(storeKey(userId));
		if (!raw) return [];
		const parsed = JSON.parse(raw) as T[];
		return Array.isArray(parsed) ? parsed : [];
	} catch {
		return [];
	}
}

export function saveThreads<T>(userId: number, threads: T[]) {
	try {
		// Cap storage: most recent 50 threads.
		localStorage.setItem(
			storeKey(userId),
			JSON.stringify(threads.slice(0, 50)),
		);
	} catch {
		/* storage full/unavailable — chat still works, just unsaved */
	}
}

/** Remove every thread store on this device (all users + the legacy key). */
export function clearThreadStores() {
	try {
		const doomed: string[] = [];
		for (let i = 0; i < localStorage.length; i++) {
			const key = localStorage.key(i);
			if (key === LEGACY_KEY || key?.startsWith(`${STORE_PREFIX}:`)) {
				doomed.push(key);
			}
		}
		for (const key of doomed) localStorage.removeItem(key);
	} catch {
		/* storage unavailable — nothing persisted, nothing to clear */
	}
}
