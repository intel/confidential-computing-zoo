//go:build !windows
// +build !windows

package config

func validateOSConfig(*Config) error {
	return nil
}
