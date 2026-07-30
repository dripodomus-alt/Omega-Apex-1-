import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { User, onAuthStateChanged, signInWithPopup, signOut } from "firebase/auth";
import { doc, getDoc, setDoc } from "firebase/firestore";
import { auth, googleAuthProvider, db } from "../lib/firebase.ts";
import { handleFirestoreError, OperationType } from "../lib/firebaseError.ts";

interface FirebaseContextType {
  user: User | null;
  loading: boolean;
  operatorRole: string | null;
  signInWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
}

const FirebaseContext = createContext<FirebaseContextType | undefined>(undefined);

export function FirebaseProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [operatorRole, setOperatorRole] = useState<string | null>(null);

  const syncOperatorProfile = useCallback(async (firebaseUser: User) => {
    const operatorRef = doc(db, "operators", firebaseUser.uid);
    try {
      const docSnap = await getDoc(operatorRef);
      if (docSnap.exists()) {
        const data = docSnap.data();
        setOperatorRole(data.role || "operator");
      } else {
        // Create operator record in Firestore with "operator" role
        const payload = {
          uid: firebaseUser.uid,
          email: firebaseUser.email || "",
          role: "operator",
          lastLogin: new Date().toISOString(),
        };
        await setDoc(operatorRef, payload);
        setOperatorRole("operator");
      }
    } catch (err) {
      // Gracefully log or handle using our error wrapper
      console.error("Failed to sync operator profile:", err);
      try {
        handleFirestoreError(err, OperationType.WRITE, `operators/${firebaseUser.uid}`);
      } catch (wrappedErr) {
        // Fallback to let auth complete even if write rules fail initially
      }
    }
  }, []);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      setUser(firebaseUser);
      if (firebaseUser) {
        await syncOperatorProfile(firebaseUser);
      } else {
        setOperatorRole(null);
      }
      setLoading(false);
    });

    return () => unsubscribe();
  }, [syncOperatorProfile]);

  const signInWithGoogle = useCallback(async () => {
    setLoading(true);
    try {
      await signInWithPopup(auth, googleAuthProvider);
    } catch (err) {
      console.error("Sign-in failed:", err);
      setLoading(false);
      throw err;
    }
  }, []);

  const logout = useCallback(async () => {
    setLoading(true);
    try {
      await signOut(auth);
    } catch (err) {
      console.error("Logout failed:", err);
      setLoading(false);
      throw err;
    }
  }, []);

  return (
    <FirebaseContext.Provider
      value={{
        user,
        loading,
        operatorRole,
        signInWithGoogle,
        logout,
      }}
    >
      {children}
    </FirebaseContext.Provider>
  );
}

export function useFirebase() {
  const context = useContext(FirebaseContext);
  if (context === undefined) {
    throw new Error("useFirebase must be used within a FirebaseProvider");
  }
  return context;
}
