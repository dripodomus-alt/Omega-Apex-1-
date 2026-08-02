#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

function readJson(filePath) {
  if (!fs.existsSync(filePath)) return null;
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function writeJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
}

function inferPackageManager(repoRoot) {
  const packageJsonPath = path.join(repoRoot, 'package.json');
  if (fs.existsSync(packageJsonPath)) return 'npm';
  return 'npm';
}

function buildBootstrapPlan(options = {}) {
  const repoRoot = options.repoRoot || process.cwd();
  const packageJsonPath = options.packageJsonPath || path.join(repoRoot, 'package.json');
  const requirementsPath = options.requirementsPath || path.join(repoRoot, 'requirements.txt');
  const statePath = options.statePath || path.join(repoRoot, 'out', 'bootstrap-dependencies-state.json');
  const nodeModulesPath = options.nodeModulesPath || path.join(repoRoot, 'node_modules');
  const pythonInstalled = options.pythonInstalled !== false;

  const hasPackageJson = fs.existsSync(packageJsonPath);
  const hasRequirements = fs.existsSync(requirementsPath);
  const nodeModulesExists = fs.existsSync(nodeModulesPath);
  const state = readJson(statePath);

  const nodeInstallRequired = hasPackageJson && !nodeModulesExists;
  const pythonInstallRequired = hasRequirements && !state?.pythonDepsInstalled;

  return {
    repoRoot,
    packageJsonPath,
    requirementsPath,
    statePath,
    nodeModulesPath,
    hasPackageJson,
    hasRequirements,
    nodeModulesExists,
    pythonInstalled,
    nodeInstallRequired,
    pythonInstallRequired,
    lastAttemptedAt: state?.lastAttemptedAt || null,
  };
}

function writeDependencyState(statePath, plan) {
  const state = {
    ...plan,
    lastAttemptedAt: new Date().toISOString(),
    pythonDepsInstalled: plan.pythonInstalled && !plan.pythonInstallRequired,
    nodeDepsInstalled: !plan.nodeInstallRequired,
  };
  writeJson(statePath, state);
  return state;
}

function ensureBootstrapDependencies(options = {}) {
  const plan = buildBootstrapPlan(options);
  const statePath = plan.statePath;
  const repoRoot = plan.repoRoot;

  if (!plan.pythonInstalled) {
    console.warn('[bootstrap] Python runtime not available; skipping Python dependency install.');
    return { ...plan, skipped: true, reason: 'python-unavailable' };
  }

  const steps = [];
  if (plan.nodeInstallRequired) {
    const manager = inferPackageManager(repoRoot);
    const install = spawnSync(manager, ['install', '--no-fund', '--no-audit'], {
      cwd: repoRoot,
      stdio: 'inherit',
      env: process.env,
    });
    if (install.status !== 0) {
      throw new Error(`[bootstrap] ${manager} install failed with exit code ${install.status}`);
    }
    steps.push(`${manager} install`);
  }

  if (plan.pythonInstallRequired) {
    const install = spawnSync(process.platform === 'win32' ? 'py' : 'python3', ['-m', 'pip', 'install', '-r', plan.requirementsPath], {
      cwd: repoRoot,
      stdio: 'inherit',
      env: process.env,
    });
    if (install.status !== 0) {
      throw new Error(`[bootstrap] python dependency install failed with exit code ${install.status}`);
    }
    steps.push('python pip install');
  }

  const state = writeDependencyState(statePath, { ...plan, steps });
  return { ...state, steps, ok: true };
}

if (require.main === module) {
  try {
    const result = ensureBootstrapDependencies();
    console.log('[bootstrap] dependency bootstrap complete');
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    console.error(`[bootstrap] ${error.message}`);
    process.exit(1);
  }
}

module.exports = {
  buildBootstrapPlan,
  writeDependencyState,
  ensureBootstrapDependencies,
};
