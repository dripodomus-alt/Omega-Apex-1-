import { ArbitrageRoute } from '../types';

export interface DriveFileItem {
  id: string;
  name: string;
  mimeType: string;
  size?: string;
  createdTime?: string;
  modifiedTime?: string;
  webViewLink?: string;
  iconLink?: string;
}

/**
 * List files in user's Google Drive
 */
export async function listDriveFiles(accessToken: string): Promise<DriveFileItem[]> {
  try {
    const response = await fetch(
      'https://www.googleapis.com/drive/v3/files?pageSize=50&orderBy=modifiedTime%20desc&fields=files(id,name,mimeType,size,createdTime,modifiedTime,webViewLink,iconLink)',
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      }
    );

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`Drive API Error (${response.status}): ${errText}`);
    }

    const data = await response.json();
    return data.files || [];
  } catch (error) {
    console.error('Error listing Drive files:', error);
    throw error;
  }
}

/**
 * Create or locate a folder in Google Drive
 */
export async function ensureDriveFolder(accessToken: string, folderName: string): Promise<string> {
  // Check if folder exists
  const query = encodeURIComponent(`name = '${folderName}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false`);
  const checkRes = await fetch(`https://www.googleapis.com/drive/v3/files?q=${query}&fields=files(id,name)`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (checkRes.ok) {
    const data = await checkRes.json();
    if (data.files && data.files.length > 0) {
      return data.files[0].id;
    }
  }

  // Create folder
  const createRes = await fetch('https://www.googleapis.com/drive/v3/files', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      name: folderName,
      mimeType: 'application/vnd.google-apps.folder',
    }),
  });

  if (!createRes.ok) {
    throw new Error('Failed to create folder in Google Drive');
  }

  const folderData = await createRes.json();
  return folderData.id;
}

/**
 * Save an Arbitrage Route audit JSON backup into Google Drive
 */
export async function saveRouteBackupToDrive(
  accessToken: string,
  route: ArbitrageRoute,
  folderId?: string
): Promise<DriveFileItem> {
  const metadata = {
    name: `OMEGA_Route_${route.id}_${Date.now()}.json`,
    mimeType: 'application/json',
    ...(folderId ? { parents: [folderId] } : {}),
  };

  const backupContent = {
    app: 'OMEGA V5 MEV Arbitrage Engine',
    exportedAt: new Date().toISOString(),
    routeId: route.id,
    path: route.pathString,
    optimalInputUSD: route.optimalInputUSD,
    expectedYieldUSD: route.expectedYieldUSD,
    netProfitUSD: route.netProfitUSD,
    vqcAlphaScore: route.vqcAlphaScore,
    vqcWinProbability: route.vqcWinProbability,
    stage: route.stage,
    pools: route.pools,
    notes: route.notes,
  };

  const form = new FormData();
  form.append('metadata', new Blob([JSON.stringify(metadata)], { type: 'application/json' }));
  form.append('file', new Blob([JSON.stringify(backupContent, null, 2)], { type: 'application/json' }));

  const res = await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,mimeType,size,createdTime,webViewLink', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    body: form,
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Upload failed: ${err}`);
  }

  return await res.json();
}

/**
 * Delete a file from Google Drive (Requires explicit UI confirmation!)
 */
export async function deleteDriveFile(accessToken: string, fileId: string): Promise<boolean> {
  const res = await fetch(`https://www.googleapis.com/drive/v3/files/${fileId}`, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  return res.ok;
}
