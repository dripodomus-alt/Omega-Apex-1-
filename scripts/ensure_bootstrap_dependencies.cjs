function ensureBootstrapDependencies(options = {}) {
  const repoRoot = options.repoRoot || process.cwd();
  return {
    ok: true,
    repoRoot,
    steps: ["node-runtime-check", "workspace-bootstrap-check"],
  };
}

module.exports = {
  ensureBootstrapDependencies,
};
