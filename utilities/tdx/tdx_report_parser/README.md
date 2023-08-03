# TDX Report Generate and Parse Tool

## Setup Compile Dependencies

For Ubuntu 22.04

```
echo "deb [arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu jammy main" > /etc/apt/sources.list.d/intel-sgx.list
apt update
apt install -y libtdx-attest libtdx-attest-dev
```

For RHEL 8.x

```
wget https://download.01.org/intel-sgx/sgx-dcap/${DCAP_VERSION}/linux/distro/rhel8.6-server/sgx_rpm_local_repo.tgz

tar -zxvf sgx_rpm_local_repo.tar.gz
mv sgx_rpm_local_repo /srv/sgx_rpm_local_repo

# Setup local RPM repository
cat <<EOF >> /etc/yum.repos.d/tdx-attestation.repo
[tdx-attestation-local]
name=tdx-attestation-local
baseurl=file:///srv/sgx_rpm_local_repo
enabled=1
gpgcheck=0
module_hotfixes=true
EOF

dnf check-update
dnf install -y libtdx-attest libtdx-attest-devel
```

## Build

```
make
```

## Program Flags

"-p" or "--path": load or save tdx report file path.

"-m" or "--mode": run mode.
- gen mode (-m=0): generate tdx report to file, should be executed in a TDVM.
- gen and parse mode (-m=1): generate and parse tdx report, should be executed in a TDVM.
- parse mode (-m=2): parse tdx report from file, could be executed in the TDX and Non-TDX linux system.

## Get TDX Report

One step to get TDX report:
1. gen and parse tdx report (TDVM)

    ```
    ./tdx_report.out
    # or
    ./tdx_report.out -m=1
    ```

Two steps to get TDX report:
1. gen tdx report to file (TDVM)

    ```
    ./tdx_report.out -m=0 -p="tdx_report.data"
    ```

2. parse tdx report from file (TDX or Non-TD linux system)

    ```
    ./tdx_report.out -m=2 -p="tdx_report.data"
    ```

## Outputs

```
TD info
attributes: 0x0000000010000000 (NO_DEBUG SEPT_VE_DISABLE)
xfam: 0x0000000000061ae7
mr_td: a4a003346c5a19a6fd250471e872bd071d8c92d7431abda463417808a17383aa0d42987814bc92f5f59c6044b677f514
mr_config_id: 000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
mr_owner: 000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
mr_owner_config: 000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
rtmr0: 419f603bf91259399dc65e3fbc6fefac63ae2ac4c78615496763e0a25c34b4471a9c5298ee2e21f720c1f913cc38f06e
rtmr1: 22e6adf1051970281455f9eba5a5fb6c161ff8df9e59a36c4882c607a1028fdc16ae19885a169e00f83ed3c09329ed19
rtmr2: e6062f5a1327f49bddbedbff5724b5ef5eb19402f1ce81934d761eefb7edb187233a9677006024752cd4afdecb412a9a
rtmr3: 000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
```