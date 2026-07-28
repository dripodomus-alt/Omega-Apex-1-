import React, { useState, useEffect } from 'react';
import { User } from 'firebase/auth';
import { ArbitrageRoute } from '../types';
import { initAuth, googleSignIn, logout } from '../lib/firebaseAuth';
import {
  listDriveFiles,
  saveRouteBackupToDrive,
  ensureDriveFolder,
  deleteDriveFile,
  DriveFileItem,
} from '../lib/googleDriveService';
import {
  HardDrive,
  CloudUpload,
  RefreshCw,
  Trash2,
  ExternalLink,
  FolderPlus,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  FileJson,
  LogOut,
  Dna,
  Lock,
} from 'lucide-react';

interface GoogleDriveManagerProps {
  routes: ArbitrageRoute[];
}

export const GoogleDriveManager: React.FC<GoogleDriveManagerProps> = ({ routes }) => {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [needsAuth, setNeedsAuth] = useState<boolean>(true);
  const [isLoggingIn, setIsLoggingIn] = useState<boolean>(false);

  const [driveFiles, setDriveFiles] = useState<DriveFileItem[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState<boolean>(false);
  const [isSyncingAll, setIsSyncingAll] = useState<boolean>(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);

  // File Deletion Modal State
  const [fileToDelete, setFileToDelete] = useState<DriveFileItem | null>(null);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  // Batch Selection State for Drive Files
  const [selectedDriveFileIds, setSelectedDriveFileIds] = useState<string[]>([]);
  const [isBatchDeleting, setIsBatchDeleting] = useState<boolean>(false);

  // Toggle selection
  const toggleSelectAllDriveFiles = () => {
    if (selectedDriveFileIds.length === driveFiles.length) {
      setSelectedDriveFileIds([]);
    } else {
      setSelectedDriveFileIds(driveFiles.map((f) => f.id));
    }
  };

  const toggleSelectDriveFile = (id: string) => {
    setSelectedDriveFileIds((prev) =>
      prev.includes(id) ? prev.filter((fId) => fId !== id) : [...prev, id]
    );
  };

  const handleBatchDeleteDriveFiles = async () => {
    if (selectedDriveFileIds.length === 0 || !accessToken) return;
    setIsBatchDeleting(true);
    setSyncStatus(`Batch deleting ${selectedDriveFileIds.length} files from Google Drive...`);

    try {
      let count = 0;
      for (const id of selectedDriveFileIds) {
        await deleteDriveFile(accessToken, id);
        count++;
      }
      setSyncStatus(`Batch delete complete: Removed ${count} files from Google Drive.`);
      setSelectedDriveFileIds([]);
      await loadDriveFiles();
    } catch (err: any) {
      setSyncStatus(`Batch Delete Error: ${err.message || 'Failed'}`);
    } finally {
      setIsBatchDeleting(false);
    }
  };

  // Initialize Auth state listener on mount
  useEffect(() => {
    const unsubscribe = initAuth(
      (currentUser, token) => {
        setUser(currentUser);
        setAccessToken(token);
        setNeedsAuth(false);
      },
      () => {
        setUser(null);
        setAccessToken(null);
        setNeedsAuth(true);
      }
    );

    return () => unsubscribe();
  }, []);

  // Fetch Drive Files when authenticated
  useEffect(() => {
    if (accessToken) {
      loadDriveFiles();
    }
  }, [accessToken]);

  const loadDriveFiles = async () => {
    if (!accessToken) return;
    setIsLoadingFiles(true);
    try {
      const files = await listDriveFiles(accessToken);
      setDriveFiles(files);
    } catch (err: any) {
      console.error('Error loading Drive files:', err);
      setSyncStatus(`Failed to fetch Drive files: ${err.message || 'Error'}`);
    } finally {
      setIsLoadingFiles(false);
    }
  };

  const handleLogin = async () => {
    setIsLoggingIn(true);
    setSyncStatus(null);
    try {
      const result = await googleSignIn();
      if (result) {
        setUser(result.user);
        setAccessToken(result.accessToken);
        setNeedsAuth(false);
        setSyncStatus('Successfully authenticated with Google Drive.');
      }
    } catch (err: any) {
      console.error('Google login failed:', err);
      setSyncStatus(`Sign-In Failed: ${err.message || 'Cancelled'}`);
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    setUser(null);
    setAccessToken(null);
    setNeedsAuth(true);
    setDriveFiles([]);
    setSyncStatus('Logged out of Google Drive.');
  };

  // Sync all routes to Google Drive
  const handleBackupAllRoutes = async () => {
    if (!accessToken) return;
    setIsSyncingAll(true);
    setSyncStatus('Creating Google Drive "OMEGA_MEV_Backups" folder...');

    try {
      const folderId = await ensureDriveFolder(accessToken, 'OMEGA_MEV_Backups');
      setSyncStatus(`Uploading ${routes.length} staged routes to Google Drive folder...`);

      let count = 0;
      for (const route of routes) {
        await saveRouteBackupToDrive(accessToken, route, folderId);
        count++;
      }

      setSyncStatus(`Successfully backed up ${count} routes to Google Drive.`);
      await loadDriveFiles();
    } catch (err: any) {
      console.error('Backup error:', err);
      setSyncStatus(`Backup Error: ${err.message || 'Failed'}`);
    } finally {
      setIsSyncingAll(false);
    }
  };

  // Backup single route
  const handleBackupSingleRoute = async (route: ArbitrageRoute) => {
    if (!accessToken) return;
    setSyncStatus(`Backing up route ${route.id}...`);

    try {
      const folderId = await ensureDriveFolder(accessToken, 'OMEGA_MEV_Backups');
      const file = await saveRouteBackupToDrive(accessToken, route, folderId);
      setSyncStatus(`Successfully backed up route ${route.id} to Google Drive (${file.name}).`);
      await loadDriveFiles();
    } catch (err: any) {
      setSyncStatus(`Failed to backup route ${route.id}: ${err.message}`);
    }
  };

  // Destructive Delete File Confirmation Handler
  const confirmDeleteFile = async () => {
    if (!fileToDelete || !accessToken) return;
    setIsDeleting(true);
    try {
      const success = await deleteDriveFile(accessToken, fileToDelete.id);
      if (success) {
        setSyncStatus(`Deleted file "${fileToDelete.name}" from Google Drive.`);
        setDriveFiles((prev) => prev.filter((f) => f.id !== fileToDelete.id));
      } else {
        setSyncStatus(`Failed to delete file "${fileToDelete.name}".`);
      }
    } catch (err: any) {
      setSyncStatus(`Delete Error: ${err.message}`);
    } finally {
      setIsDeleting(false);
      setFileToDelete(null);
    }
  };

  return (
    <div id="google-drive-manager" className="space-y-6">
      {/* Top Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-indigo-950 border border-indigo-800/80 rounded-xl text-indigo-400">
              <HardDrive className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                  Google Drive Cloud Vault & Route Backup Synchronizer
                </h2>
                <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800/80 text-[10px] font-mono rounded font-bold">
                  OAuth Active
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1 max-w-2xl">
                Backup MEV route DNA parameters, calculus apex variables, and execution audit trails directly to your Google Drive account with high availability.
              </p>
            </div>
          </div>

          {/* User Profile Status or Sign In Button */}
          {user && accessToken ? (
            <div className="flex items-center gap-3 bg-slate-950 p-2.5 rounded-xl border border-slate-800">
              {user.photoURL && (
                <img
                  src={user.photoURL}
                  alt={user.displayName || 'Google User'}
                  className="w-8 h-8 rounded-full border border-emerald-500/50"
                />
              )}
              <div className="text-xs font-mono">
                <div className="text-white font-bold">{user.displayName || 'Google Account'}</div>
                <div className="text-slate-400 text-[10px] truncate max-w-[160px]">{user.email}</div>
              </div>

              <button
                onClick={handleLogout}
                className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition-all ml-1"
                title="Sign out of Google Drive"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <button
              onClick={handleLogin}
              disabled={isLoggingIn}
              className="gsi-material-button font-mono text-xs shadow-lg hover:brightness-110 active:scale-95 transition-all"
              style={{
                backgroundColor: '#1f2937',
                color: '#ffffff',
                border: '1px solid #374151',
                padding: '8px 16px',
                borderRadius: '8px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '12px',
                cursor: 'pointer',
              }}
            >
              <div className="gsi-material-button-icon">
                <svg
                  version="1.1"
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 48 48"
                  style={{ display: 'block', width: '20px', height: '20px' }}
                >
                  <path
                    fill="#EA4335"
                    d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
                  ></path>
                  <path
                    fill="#4285F4"
                    d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
                  ></path>
                  <path
                    fill="#FBBC05"
                    d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
                  ></path>
                  <path
                    fill="#34A853"
                    d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
                  ></path>
                  <path fill="none" d="M0 0h48v48H0z"></path>
                </svg>
              </div>
              <span className="font-semibold text-xs">
                {isLoggingIn ? 'Connecting to Google...' : 'Sign in with Google Drive'}
              </span>
            </button>
          )}
        </div>
      </div>

      {/* Sync Status Toast Alert */}
      {syncStatus && (
        <div className="bg-slate-900 border border-indigo-800/80 p-3.5 rounded-xl font-mono text-xs flex items-center justify-between text-indigo-300">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{syncStatus}</span>
          </div>
          <button
            onClick={() => setSyncStatus(null)}
            className="text-slate-400 hover:text-white text-[10px] uppercase font-bold"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Backup Controls & Route Quick Sync */}
        <div className="space-y-6 lg:col-span-1">
          {/* Quick Actions Panel */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono flex items-center gap-2 border-b border-slate-800 pb-2">
              <CloudUpload className="w-4 h-4 text-emerald-400" />
              <span>Google Drive Cloud Actions</span>
            </h3>

            <button
              onClick={handleBackupAllRoutes}
              disabled={needsAuth || isSyncingAll}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-mono text-xs font-bold rounded-xl shadow-lg transition-all active:scale-95"
            >
              {isSyncingAll ? (
                <RefreshCw className="w-4 h-4 animate-spin text-white" />
              ) : (
                <CloudUpload className="w-4 h-4 text-emerald-200" />
              )}
              <span>
                {needsAuth
                  ? 'Sign in to Backup Routes'
                  : isSyncingAll
                  ? 'Uploading to Drive...'
                  : `Sync All Staged Routes (${routes.length}) to Drive`}
              </span>
            </button>

            <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 font-mono text-[11px] space-y-1.5 text-slate-300">
              <div className="flex justify-between text-slate-400">
                <span>Target Folder:</span>
                <span className="text-emerald-400 font-semibold">OMEGA_MEV_Backups</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Format:</span>
                <span className="text-indigo-300 font-semibold">JSON Audit Snapshot</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Auth Scope:</span>
                <span className="text-white font-semibold">https://.../auth/drive</span>
              </div>
            </div>
          </div>

          {/* Staged Route Individual Backup List */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg space-y-3">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider font-mono flex items-center justify-between">
              <span>Individual Route Backup</span>
              <span className="text-emerald-400">{routes.length} Available</span>
            </h3>

            <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
              {routes.map((route, idx) => (
                <div
                  key={`${route.id}-${idx}`}
                  className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs font-mono space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-white">{route.id}</span>
                    <span className="text-emerald-400 font-bold">+${route.netProfitUSD.toLocaleString()}</span>
                  </div>
                  <div className="text-[10px] text-slate-400 truncate">{route.pathString}</div>
                  <button
                    onClick={() => handleBackupSingleRoute(route)}
                    disabled={needsAuth}
                    className="w-full py-1.5 bg-indigo-950 hover:bg-indigo-900 border border-indigo-800/80 text-indigo-300 rounded text-[11px] font-bold transition-all disabled:opacity-50 flex items-center justify-center gap-1.5"
                  >
                    <CloudUpload className="w-3 h-3 text-indigo-400" />
                    <span>Upload Snapshot to Drive</span>
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: Drive File Explorer & Vault List */}
        <div className="space-y-6 lg:col-span-2">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <FileJson className="w-5 h-5 text-emerald-400" />
                <h3 className="text-sm font-bold text-white font-mono uppercase tracking-wider">
                  Google Drive File Explorer & Vault Catalog
                </h3>
              </div>

              <button
                onClick={loadDriveFiles}
                disabled={needsAuth || isLoadingFiles}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-mono font-bold transition-all disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoadingFiles ? 'animate-spin' : ''}`} />
                <span>Refresh Drive</span>
              </button>
            </div>

            {needsAuth ? (
              <div className="bg-slate-950 p-8 rounded-xl border border-slate-800 text-center space-y-4">
                <Lock className="w-10 h-10 text-slate-600 mx-auto" />
                <div className="text-sm font-mono text-slate-300 font-bold">
                  Google Drive Connection Required
                </div>
                <p className="text-xs font-mono text-slate-400 max-w-md mx-auto">
                  Sign in with your Google account above to unlock listing, viewing, and organizing MEV route backups directly inside Google Drive.
                </p>
                <button
                  onClick={handleLogin}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-mono font-bold transition-all"
                >
                  Connect Google Drive Account
                </button>
              </div>
            ) : isLoadingFiles ? (
              <div className="bg-slate-950 p-8 rounded-xl border border-slate-800 text-center space-y-2">
                <RefreshCw className="w-6 h-6 text-emerald-400 animate-spin mx-auto" />
                <div className="text-xs font-mono text-slate-400">Fetching files from Google Drive...</div>
              </div>
            ) : driveFiles.length === 0 ? (
              <div className="bg-slate-950 p-8 rounded-xl border border-slate-800 text-center space-y-3">
                <FolderPlus className="w-10 h-10 text-slate-600 mx-auto" />
                <div className="text-sm font-mono text-slate-300 font-bold">
                  No Backups Found in Google Drive
                </div>
                <p className="text-xs font-mono text-slate-400 max-w-md mx-auto">
                  Click "Sync All Staged Routes" on the left to upload your route snapshots into Google Drive.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="text-xs font-mono text-slate-400 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span>Drive Catalog ({driveFiles.length} items)</span>
                    <span className="text-emerald-400 font-semibold">• Connected</span>
                  </div>

                  {selectedDriveFileIds.length > 0 && (
                    <button
                      onClick={handleBatchDeleteDriveFiles}
                      disabled={isBatchDeleting}
                      className="flex items-center gap-1.5 px-3 py-1 bg-rose-600 hover:bg-rose-500 text-white rounded text-xs font-bold transition-all shadow"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>
                        {isBatchDeleting
                          ? 'Deleting Batch...'
                          : `Batch Delete Selected (${selectedDriveFileIds.length})`}
                      </span>
                    </button>
                  )}
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 bg-slate-950">
                        <th className="p-3 w-8">
                          <button
                            onClick={toggleSelectAllDriveFiles}
                            className="text-slate-400 hover:text-emerald-400"
                            title="Select All Drive Files"
                          >
                            {selectedDriveFileIds.length === driveFiles.length ? (
                              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                            ) : (
                              <span className="w-4 h-4 rounded border border-slate-600 inline-block"></span>
                            )}
                          </button>
                        </th>
                        <th className="p-3">File Name</th>
                        <th className="p-3">Type</th>
                        <th className="p-3">Modified Date</th>
                        <th className="p-3">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {driveFiles.map((file) => {
                        const isSelected = selectedDriveFileIds.includes(file.id);
                        return (
                          <tr
                            key={file.id}
                            className={`hover:bg-slate-800/40 transition-colors ${
                              isSelected ? 'bg-indigo-950/20' : ''
                            }`}
                          >
                            <td className="p-3">
                              <button
                                onClick={() => toggleSelectDriveFile(file.id)}
                                className="text-slate-400 hover:text-emerald-400"
                              >
                                {isSelected ? (
                                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                                ) : (
                                  <span className="w-4 h-4 rounded border border-slate-700 inline-block"></span>
                                )}
                              </button>
                            </td>
                            <td className="p-3 font-bold text-slate-200">
                              <div className="flex items-center gap-2">
                                <FileJson className="w-4 h-4 text-emerald-400 shrink-0" />
                                <span className="truncate max-w-xs">{file.name}</span>
                              </div>
                            </td>
                            <td className="p-3 text-indigo-300 text-[11px]">
                              {file.mimeType.includes('folder')
                                ? 'Google Drive Folder'
                                : file.mimeType.includes('json')
                                ? 'JSON Route Snapshot'
                                : 'Document'}
                            </td>
                            <td className="p-3 text-slate-400 text-[11px]">
                              {file.modifiedTime
                                ? new Date(file.modifiedTime).toLocaleString()
                                : 'Recently'}
                            </td>
                            <td className="p-3">
                              <div className="flex items-center gap-2">
                                {file.webViewLink && (
                                  <a
                                    href={file.webViewLink}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="p-1.5 bg-indigo-950 hover:bg-indigo-900 text-indigo-300 rounded border border-indigo-800/80"
                                    title="Open in Google Drive"
                                  >
                                    <ExternalLink className="w-3.5 h-3.5" />
                                  </a>
                                )}
                                <button
                                  onClick={() => setFileToDelete(file)}
                                  className="p-1.5 bg-rose-950 hover:bg-rose-900 text-rose-300 rounded border border-rose-800/80"
                                  title="Delete file from Google Drive"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Destructive Deletion Modal Safeguard (Mandatory per User Confirmation Rule) */}
      {fileToDelete && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-rose-800/80 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl font-mono">
            <div className="flex items-center gap-3 text-rose-400">
              <AlertCircle className="w-6 h-6 shrink-0" />
              <h3 className="text-base font-bold text-white">Confirm Delete from Google Drive</h3>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              Are you sure you want to delete file <strong className="text-amber-300">"{fileToDelete.name}"</strong> (ID: {fileToDelete.id.slice(0, 10)}...) from your Google Drive?
            </p>

            <p className="text-[11px] text-slate-400 bg-slate-950 p-3 rounded-lg border border-slate-800">
              This will permanently remove the item from Google Drive.
            </p>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setFileToDelete(null)}
                disabled={isDeleting}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-bold transition-all"
              >
                Cancel
              </button>

              <button
                onClick={confirmDeleteFile}
                disabled={isDeleting}
                className="flex items-center gap-2 px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-xs font-bold transition-all shadow-lg active:scale-95 disabled:opacity-50"
              >
                {isDeleting ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Trash2 className="w-3.5 h-3.5" />
                )}
                <span>{isDeleting ? 'Deleting...' : 'Confirm Permanent Delete'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
