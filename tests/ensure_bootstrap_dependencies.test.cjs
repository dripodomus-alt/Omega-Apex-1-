const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const os = require('node:os');
const fs = require('node:fs');

const { buildBootstrapPlan, writeDependencyState } = require('../scripts/ensure_bootstrap_dependencies.cjs');

test('buildBootstrapPlan reports node installation when install state is missing', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'omega-bootstrap-'));
  const packageJsonPath = path.join(tmpDir, 'package.json');
  const requirementsPath = path.join(tmpDir, 'requirements.txt');
  const statePath = path.join(tmpDir, 'state.json');

  fs.writeFileSync(packageJsonPath, '{"name":"demo"}\n');
  fs.writeFileSync(requirementsPath, 'web3\n');

  const plan = buildBootstrapPlan({
    repoRoot: tmpDir,
    packageJsonPath,
    requirementsPath,
    statePath,
    nodeModulesPath: path.join(tmpDir, 'node_modules'),
    pythonInstalled: true,
  });

  assert.equal(plan.nodeInstallRequired, true);
  assert.equal(plan.pythonInstallRequired, true);

  const updated = writeDependencyState(statePath, plan);
  assert.equal(updated.nodeInstallRequired, true);
  assert.equal(updated.pythonInstallRequired, true);
});
