import {
  collection,
  doc,
  setDoc,
  getDocs,
  onSnapshot,
  deleteDoc,
  query,
} from 'firebase/firestore';
import { db, auth, OperationType, handleFirestoreError } from './firebase';
import { ArbitrageRoute, SimulationAuditLog } from '../types';

const ROUTES_COLLECTION = 'routes';
const AUDIT_LOGS_COLLECTION = 'auditLogs';

/**
 * Save or sync a route to Firestore
 */
export async function syncRouteToFirestore(route: ArbitrageRoute): Promise<void> {
  const path = `${ROUTES_COLLECTION}/${route.id}`;
  try {
    const routeData = {
      ...route,
      userId: auth.currentUser?.uid || 'anonymous',
    };
    await setDoc(doc(db, ROUTES_COLLECTION, route.id), routeData, { merge: true });
  } catch (error) {
    handleFirestoreError(error, OperationType.WRITE, path);
  }
}

/**
 * Fetch all routes from Firestore
 */
export async function fetchRoutesFromFirestore(): Promise<ArbitrageRoute[]> {
  const path = ROUTES_COLLECTION;
  try {
    const snapshot = await getDocs(collection(db, ROUTES_COLLECTION));
    const routes: ArbitrageRoute[] = [];
    snapshot.forEach((docSnap) => {
      routes.push(docSnap.data() as ArbitrageRoute);
    });
    return routes;
  } catch (error) {
    handleFirestoreError(error, OperationType.LIST, path);
    return [];
  }
}

/**
 * Real-time listener for Firestore routes
 */
export function subscribeRoutesFromFirestore(
  onNext: (routes: ArbitrageRoute[]) => void
): () => void {
  const path = ROUTES_COLLECTION;
  const q = query(collection(db, ROUTES_COLLECTION));

  return onSnapshot(
    q,
    (snapshot) => {
      const routes: ArbitrageRoute[] = [];
      snapshot.forEach((docSnap) => {
        routes.push(docSnap.data() as ArbitrageRoute);
      });
      onNext(routes);
    },
    (error) => {
      handleFirestoreError(error, OperationType.GET, path);
    }
  );
}

/**
 * Save an audit log to Firestore
 */
export async function syncAuditLogToFirestore(auditLog: SimulationAuditLog): Promise<void> {
  const path = `${AUDIT_LOGS_COLLECTION}/${auditLog.id}`;
  try {
    const logData = {
      ...auditLog,
      userId: auth.currentUser?.uid || 'anonymous',
    };
    await setDoc(doc(db, AUDIT_LOGS_COLLECTION, auditLog.id), logData, { merge: true });
  } catch (error) {
    handleFirestoreError(error, OperationType.WRITE, path);
  }
}

/**
 * Real-time listener for Audit Logs from Firestore
 */
export function subscribeAuditLogsFromFirestore(
  onNext: (logs: SimulationAuditLog[]) => void
): () => void {
  const path = AUDIT_LOGS_COLLECTION;
  const q = query(collection(db, AUDIT_LOGS_COLLECTION));

  return onSnapshot(
    q,
    (snapshot) => {
      const logs: SimulationAuditLog[] = [];
      snapshot.forEach((docSnap) => {
        logs.push(docSnap.data() as SimulationAuditLog);
      });
      onNext(logs);
    },
    (error) => {
      handleFirestoreError(error, OperationType.GET, path);
    }
  );
}
