// Command server serves the Server-side Argus TDX NodeAttestor plugin to SPIRE.
package main

import (
	"github.com/spiffe/spire-plugin-sdk/pluginmain"
	nodeattestorapi "github.com/spiffe/spire-plugin-sdk/proto/spire/plugin/server/nodeattestor/v1"
	configapi "github.com/spiffe/spire-plugin-sdk/proto/spire/service/common/config/v1"

	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/server"
)

func main() {
	plugin := server.New()
	pluginmain.Serve(
		nodeattestorapi.NodeAttestorPluginServer(plugin),
		configapi.ConfigServiceServer(plugin),
	)
}
