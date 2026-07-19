param(
    [string]$RpcUrl = "",
    [switch]$UseFork,
    [switch]$NoEthCall
)

$ErrorActionPreference = "Stop"

$argsList = @()
if ($RpcUrl) {
    $argsList += @("--rpc-url", $RpcUrl)
}
if ($UseFork) {
    $argsList += "--use-fork"
}
if ($NoEthCall) {
    $argsList += "--no-eth-call"
}

python -m omega_v5.pipeline_validation @argsList
