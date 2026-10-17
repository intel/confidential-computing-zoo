# The complete executable payload shared by build.sh and install.sh.
# Keep installation independent of unrelated files left in a reused build directory.
ARGUS_WORKLOAD_ARTIFACTS=(
    bin/argus-tdx-nodeattestor-agent
    bin/argus-tdx-nodeattestor-server
    bin/argus-tdx-workloadattestor
    bin/argus-workload
    bin/spiffe-helper
    bin/argus-agent-config
    bin/spiffe-authz
    bin/spiffe-mtls-probe
    bin/argus-spire-evidence-provider
    spire-1.15.3/bin/spire-agent
    spire-1.15.3/bin/spire-server
)
