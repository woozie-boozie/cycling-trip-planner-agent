/**
 * Firebase Auth — every visitor gets a stable identity.
 *
 * On first load we silently sign the visitor in anonymously; they can later
 * upgrade to Google (linkWithPopup keeps the same uid, so their profile and
 * sessions follow them). Every backend call attaches the ID token — the
 * FastAPI side verifies it (src/api/auth.py).
 *
 * The web config below is public by design (Firebase web API keys are not
 * secrets; security comes from token verification + rules).
 */

import { getApps, initializeApp, type FirebaseApp } from "firebase/app";
import {
  GoogleAuthProvider,
  getAuth,
  linkWithPopup,
  onAuthStateChanged,
  signInAnonymously,
  signInWithPopup,
  type Auth,
  type User,
} from "firebase/auth";

const FIREBASE_CONFIG = {
  apiKey: "AIzaSyBSBN5gXifw_PVuVzKQLo73AOWpT_BtUkg",
  authDomain: "cycling-agent-prod.firebaseapp.com",
  projectId: "cycling-agent-prod",
  storageBucket: "cycling-agent-prod.firebasestorage.app",
  messagingSenderId: "1020337274806",
  appId: "1:1020337274806:web:59e9619661ef7859cecb17",
};

function getApp(): FirebaseApp {
  return getApps()[0] ?? initializeApp(FIREBASE_CONFIG);
}

export function getFirebaseAuth(): Auth {
  return getAuth(getApp());
}

/** Resolves once Firebase has restored (or created) the current user. */
export function ensureSignedIn(): Promise<User> {
  const auth = getFirebaseAuth();
  return new Promise((resolve, reject) => {
    const unsub = onAuthStateChanged(auth, (user) => {
      if (user) {
        unsub();
        resolve(user);
        return;
      }
      signInAnonymously(auth)
        .then((cred) => {
          unsub();
          resolve(cred.user);
        })
        .catch((err) => {
          unsub();
          reject(err);
        });
    });
  });
}

/** Current user's ID token, or null outside the browser / before sign-in. */
export async function getIdToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  try {
    const user = getFirebaseAuth().currentUser ?? (await ensureSignedIn());
    return await user.getIdToken();
  } catch {
    return null;
  }
}

/**
 * Upgrade to Google. Anonymous users are LINKED (same uid — profile and
 * sessions survive); if the Google account is already a user, we fall back
 * to a plain sign-in with that account.
 */
export async function signInWithGoogle(): Promise<User> {
  const auth = getFirebaseAuth();
  const provider = new GoogleAuthProvider();
  const current = auth.currentUser;
  if (current?.isAnonymous) {
    try {
      const cred = await linkWithPopup(current, provider);
      return cred.user;
    } catch (err: unknown) {
      const code = (err as { code?: string }).code;
      if (code !== "auth/credential-already-in-use") throw err;
    }
  }
  const cred = await signInWithPopup(auth, provider);
  return cred.user;
}
