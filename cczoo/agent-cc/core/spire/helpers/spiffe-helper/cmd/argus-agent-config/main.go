// Merge the Workload overlay into an existing Node configuration without
// changing the Node challenge/PoP contract, proof-key path, or CA settings.
package main

import (
	"bytes"
	"crypto/sha256"
	"flag"
	"fmt"
	"github.com/hashicorp/hcl"
	"github.com/hashicorp/hcl/hcl/ast"
	"github.com/hashicorp/hcl/hcl/printer"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/workload/protocol"
	"os"
	"path"
	"strings"
)

func block(list *ast.ObjectList, name string) (*ast.ObjectList, error) {
	items := list.Filter(name).Items
	if len(items) != 1 {
		return nil, fmt.Errorf("expected exactly one %s block", name)
	}
	object, ok := items[0].Val.(*ast.ObjectType)
	if !ok {
		return nil, fmt.Errorf("%s is not an object", name)
	}
	return object.List, nil
}
func key(item *ast.ObjectItem) string {
	var s string
	for _, k := range item.Keys {
		s += fmt.Sprint(k.Token.Value()) + "\x00"
	}
	return s
}
func replace(list *ast.ObjectList, item *ast.ObjectItem) {
	var items []*ast.ObjectItem
	for _, old := range list.Items {
		if key(old) != key(item) {
			items = append(items, old)
		}
	}
	list.Items = append(items, item)
}

// merge changes only the workload-related Agent settings and allowed plugins.
// Existing Node attestation, proof-key and CA configuration stays in the source AST.
func merge(source, overlay []byte) ([]byte, error) {
	src, err := hcl.Parse(string(source))
	if err != nil {
		return nil, err
	}
	over, err := hcl.Parse(string(overlay))
	if err != nil {
		return nil, err
	}
	root := src.Node.(*ast.ObjectList)
	oroot := over.Node.(*ast.ObjectList)
	agent, err := block(root, "agent")
	if err != nil {
		return nil, err
	}
	oa, err := block(oroot, "agent")
	if err != nil {
		return nil, err
	}
	// ObjectList.Filter strips the matched keys from its returned items. Keep
	// original nodes when inserting into another AST, including first setup.
	var experimental *ast.ObjectItem
	for _, item := range oa.Items {
		switch key(item) {
		case "socket_path\x00", "log_format\x00", "log_level\x00", "log_file\x00":
			replace(agent, item)
		case "experimental\x00":
			experimental = item
		}
	}
	oe, err := block(oa, "experimental")
	if err != nil {
		return nil, err
	}
	for _, item := range oe.Items {
		if key(item) != "broker\x00" {
			return nil, fmt.Errorf("overlay may only change experimental.broker")
		}
	}
	if len(agent.Filter("experimental").Items) == 0 {
		agent.Items = append(agent.Items, experimental)
	} else {
		e, err := block(agent, "experimental")
		if err != nil {
			return nil, err
		}
		for _, item := range oe.Items {
			replace(e, item)
		}
	}
	plugins, err := block(root, "plugins")
	if err != nil {
		return nil, err
	}
	op, err := block(oroot, "plugins")
	if err != nil {
		return nil, err
	}
	for _, item := range op.Items {
		k := key(item)
		if k != "WorkloadAttestor\x00argus_tdx\x00" && k != "WorkloadAttestor\x00unix\x00" {
			return nil, fmt.Errorf("overlay contains a non-Workload plugin")
		}
		replace(plugins, item)
	}
	var out bytes.Buffer
	if err = printer.Fprint(&out, src); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

// configureNode pins the selected deployment binary and Agent evidence socket
// while checking identity consistency with the existing Node configuration.
func configureNode(source []byte, role, binary, trustDomain, agentID, evidenceSocket string) ([]byte, error) {
	if protocol.ValidateAgentID(agentID) != nil || !strings.HasPrefix(agentID, "spiffe://"+trustDomain+"/") {
		return nil, fmt.Errorf("expected Agent ID must match the deployment trust domain")
	}
	contents, err := os.ReadFile(binary)
	if err != nil {
		return nil, err
	}
	tree, err := hcl.Parse(string(source))
	if err != nil {
		return nil, err
	}
	core, err := block(tree.Node.(*ast.ObjectList), role)
	if err != nil {
		return nil, err
	}
	if stringValue(core, "trust_domain") != trustDomain {
		return nil, fmt.Errorf("Node configuration trust_domain differs from deployment")
	}
	plugins, err := block(tree.Node.(*ast.ObjectList), "plugins")
	if err != nil {
		return nil, err
	}
	items := plugins.Filter("NodeAttestor", "argus_tdx").Items
	if len(items) != 1 {
		return nil, fmt.Errorf("expected one argus_tdx NodeAttestor")
	}
	obj, ok := items[0].Val.(*ast.ObjectType)
	if !ok {
		return nil, fmt.Errorf("invalid NodeAttestor")
	}
	props, err := hcl.Parse(fmt.Sprintf("plugin_cmd = %q\nplugin_checksum = %q\n", binary, fmt.Sprintf("%x", sha256.Sum256(contents))))
	if err != nil {
		return nil, err
	}
	for _, item := range props.Node.(*ast.ObjectList).Items {
		replace(obj.List, item)
	}
	data, err := block(obj.List, "plugin_data")
	if err != nil {
		return nil, err
	}
	if role == "agent" {
		if !path.IsAbs(evidenceSocket) || path.Clean(evidenceSocket) != evidenceSocket {
			return nil, fmt.Errorf("evidence-socket must be an absolute Linux path")
		}
		ep, _ := hcl.Parse(fmt.Sprintf("evidence_socket_path = %q", evidenceSocket))
		replace(data, ep.Node.(*ast.ObjectList).Items[0])
	} else if stringValue(data, "agent_id") != agentID {
		return nil, fmt.Errorf("Server NodeAttestor agent_id differs from deployment")
	}
	var out bytes.Buffer
	if err = printer.Fprint(&out, tree); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
}

func stringValue(list *ast.ObjectList, name string) string {
	items := list.Filter(name).Items
	if len(items) != 1 {
		return ""
	}
	literal, ok := items[0].Val.(*ast.LiteralType)
	if !ok {
		return ""
	}
	value, _ := literal.Token.Value().(string)
	return value
}
func run() error {
	source := flag.String("source", "", "Node Agent or Server HCL")
	overlay := flag.String("overlay", "", "generated Workload overlay HCL")
	output := flag.String("output", "", "new combined configuration")
	role := flag.String("role", "agent", "agent or server")
	nodeBinary := flag.String("node-binary", "", "required NodeAttestor binary for this deployment")
	trustDomain := flag.String("trust-domain", "", "expected deployment trust domain")
	agentID := flag.String("agent-id", "", "expected NodeAttestor Agent identity")
	evidenceSocket := flag.String("evidence-socket", "", "Agent-side Evidence Provider socket")
	flag.Parse()
	if *role != "agent" && *role != "server" {
		return fmt.Errorf("role must be agent or server")
	}
	if *nodeBinary == "" {
		return fmt.Errorf("node-binary is required")
	}
	a, err := os.ReadFile(*source)
	if err != nil {
		return err
	}
	merged := a
	if *role == "agent" {
		b, err := os.ReadFile(*overlay)
		if err != nil {
			return err
		}
		merged, err = merge(a, b)
		if err != nil {
			return err
		}
	}
	merged, err = configureNode(merged, *role, *nodeBinary, *trustDomain, *agentID, *evidenceSocket)
	if err != nil {
		return err
	}
	return os.WriteFile(*output, merged, 0600)
}
