//go:build !linux

package broker

import "fmt"

func checkTmpfs(string) error { return fmt.Errorf("Broker mode requires Linux tmpfs") }
