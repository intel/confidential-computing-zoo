package version

import "fmt"

const (
	// Base is the base version for the codebase.
	Base = "0.11.0"
)

var (
	gittag  = ""
	githash = "unk"
)

func Version() string {
	if gittag == "" {
		return fmt.Sprintf("%s-dev-%s", Base, githash)
	}
	return gittag
}
