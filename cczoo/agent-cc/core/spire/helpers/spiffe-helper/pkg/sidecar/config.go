package sidecar

import (
	"io/fs"

	"github.com/sirupsen/logrus"
)

type Config struct {
	// If true, merge intermediate certificates into Bundle file instead of SVID file.
	// This is the expected format for MySQL and some other applications.
	AddIntermediatesToBundle bool

	// The address of the Agent Workload API.
	AgentAddress string

	// The path to the process to launch.
	Cmd string

	// The arguments of the process to launch.
	CmdArgs string

	// Signal external process via PID file
	PIDFilename string

	// The directory name to store the x509s and/or JWTs.
	CertDir string

	// Permissions to use when writing x509 SVID to disk
	CertFileMode fs.FileMode

	// Permissions to use when writing x509 SVID Key to disk
	KeyFileMode fs.FileMode

	// Permissions to use when writing JWT Bundle to disk
	JWTBundleFileMode fs.FileMode

	// Permissions to use when writing JWT SVIDs to disk
	JWTSVIDFileMode fs.FileMode

	// If true, includes trust domains from federated servers in the CA bundle.
	IncludeFederatedDomains bool

	// If true, omits expired X509 certs from the bundle.
	OmitExpired bool

	// An array with the audience and file name to store the JWT SVIDs. File is Base64-encoded string.
	JWTSVIDs []JWTConfig

	// File name to be used to store JWT Bundle in JSON format.
	JWTBundleFilename string

	// The logger to use
	Log logrus.FieldLogger

	// The signal that the process to be launched expects to reload the certificates. Not supported on Windows.
	RenewSignal string

	// File name to be used to store the X.509 SVID public certificate in PEM format.
	SVIDFilename string

	// File name to be used to store the X.509 SVID private key and public certificate in PEM format.
	SVIDKeyFilename string

	// File name to be used to store the X.509 SVID Bundle in PEM format.
	SVIDBundleFilename string

	// Hint: The hint to pass to the spiffe endpoint to help select SPIFFE IDs
	Hint string

	// TODO: is there a reason for this to be exposed? and inside of config?
	ReloadExternalProcess func() error
}

type JWTConfig struct {
	// The audience for the JWT SVID to fetch
	JWTAudience string

	// The extra audiences for the JWT SVID to fetch
	JWTExtraAudiences []string

	// The filename to save the JWT SVID to
	JWTSVIDFilename string
}
