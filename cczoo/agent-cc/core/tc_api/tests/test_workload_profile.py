import os

import pytest

from tc_api.services.workload_profile import validate_luks_data_path


LUKS_UUID = "12345678-1234-5678-9abc-def012345678"


def _mountinfo_line(device, mountpoint, source="/dev/mapper/openviking"):
    escaped = str(mountpoint).replace("\\", "\\134").replace(" ", "\\040")
    return f"1 0 {device} / {escaped} rw - ext4 {source} rw\n"


def _fake_docker_host(tmp_path, mountinfo, host_root="/"):
    proc = tmp_path / "proc"
    daemon = proc / "123"
    daemon.mkdir(parents=True)
    (daemon / "comm").write_text("dockerd\n", encoding="ascii")
    (daemon / "mountinfo").write_text(mountinfo, encoding="utf-8")
    (daemon / "root").symlink_to(host_root)
    pid_file = tmp_path / "docker.pid"
    pid_file.write_text("123\n", encoding="ascii")
    return proc, pid_file


def _fake_sysfs(tmp_path, device, dm_uuid):
    sysfs = tmp_path / "sys"
    uuid = sysfs / device / "dm" / "uuid"
    uuid.parent.mkdir(parents=True)
    uuid.write_text(dm_uuid, encoding="ascii")
    return sysfs


def _device(path):
    value = path.stat().st_dev
    return f"{os.major(value)}:{os.minor(value)}"


def test_validate_luks_data_path_accepts_approved_mapping(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    device = _device(data)
    proc, pid_file = _fake_docker_host(tmp_path, _mountinfo_line(device, data))
    sysfs = _fake_sysfs(tmp_path, device, f"CRYPT-LUKS2-{LUKS_UUID}-openviking")

    validate_luks_data_path(data, LUKS_UUID, proc, pid_file, sysfs)


def test_validate_luks_data_path_rejects_non_luks_device(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    device = _device(data)
    proc, pid_file = _fake_docker_host(tmp_path, _mountinfo_line(device, data))
    sysfs = _fake_sysfs(tmp_path, device, "LVM-abc123")

    with pytest.raises(ValueError, match="LUKS device-mapper"):
        validate_luks_data_path(data, LUKS_UUID, proc, pid_file, sysfs)


def test_validate_luks_data_path_rejects_wrong_luks_uuid(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    device = _device(data)
    proc, pid_file = _fake_docker_host(tmp_path, _mountinfo_line(device, data))
    sysfs = _fake_sysfs(tmp_path, device, f"CRYPT-LUKS2-{LUKS_UUID}-openviking")

    with pytest.raises(ValueError, match="approved LUKS UUID"):
        validate_luks_data_path(data, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", proc, pid_file, sysfs)


def test_validate_luks_data_path_rejects_mount_device_mismatch(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    proc, pid_file = _fake_docker_host(tmp_path, _mountinfo_line("253:9", data))

    with pytest.raises(ValueError, match="device does not match"):
        validate_luks_data_path(data, LUKS_UUID, proc, pid_file, tmp_path / "sys")


def test_validate_luks_data_path_rejects_different_docker_host_path(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    device = _device(data)
    mountinfo = _mountinfo_line(device, data)
    host_root = tmp_path / "host-root"
    (host_root / str(data).lstrip("/")).mkdir(parents=True)
    proc, pid_file = _fake_docker_host(tmp_path, mountinfo, host_root)

    with pytest.raises(ValueError, match="different host path"):
        validate_luks_data_path(data, LUKS_UUID, proc, pid_file, tmp_path / "sys")


def test_validate_luks_data_path_rejects_writable_parent(tmp_path):
    mountpoint = tmp_path / "mount"
    mountpoint.mkdir(mode=0o777)
    mountpoint.chmod(0o777)
    data = mountpoint / "data"
    data.mkdir()
    device = _device(data)
    proc, pid_file = _fake_docker_host(tmp_path, _mountinfo_line(device, mountpoint))
    sysfs = _fake_sysfs(tmp_path, device, f"CRYPT-LUKS2-{LUKS_UUID}-openviking")

    with pytest.raises(ValueError, match="ancestors are writable"):
        validate_luks_data_path(data, LUKS_UUID, proc, pid_file, sysfs)


def test_validate_luks_data_path_rejects_writable_ancestor_above_mountpoint(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    device = _device(data)
    proc, pid_file = _fake_docker_host(tmp_path, _mountinfo_line(device, data))
    sysfs = _fake_sysfs(tmp_path, device, f"CRYPT-LUKS2-{LUKS_UUID}-openviking")
    tmp_path.chmod(0o777)
    try:
        with pytest.raises(ValueError, match="ancestors are writable"):
            validate_luks_data_path(data, LUKS_UUID, proc, pid_file, sysfs)
    finally:
        tmp_path.chmod(0o700)


def test_validate_luks_data_path_rejects_nested_mounts(tmp_path):
    data = tmp_path / "data"
    nested = data / "nested"
    nested.mkdir(parents=True)
    device = _device(data)
    proc, pid_file = _fake_docker_host(
        tmp_path,
        _mountinfo_line(device, data) + _mountinfo_line("253:9", nested, "/dev/mapper/plain"),
    )
    sysfs = _fake_sysfs(tmp_path, device, f"CRYPT-LUKS2-{LUKS_UUID}-openviking")

    with pytest.raises(ValueError, match="nested mount"):
        validate_luks_data_path(data, LUKS_UUID, proc, pid_file, sysfs)


def test_validate_luks_data_path_rejects_missing_mount_metadata(tmp_path):
    data = tmp_path / "data"
    data.mkdir()

    with pytest.raises(ValueError, match="Docker daemon host process metadata"):
        validate_luks_data_path(
            data, LUKS_UUID, tmp_path / "proc", tmp_path / "missing", tmp_path / "sys")


def test_validate_luks_data_path_rejects_unexpected_daemon_process(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    device = _device(data)
    proc, pid_file = _fake_docker_host(tmp_path, _mountinfo_line(device, data))
    (proc / "123" / "comm").write_text("not-dockerd\n", encoding="ascii")

    with pytest.raises(ValueError, match="does not identify dockerd"):
        validate_luks_data_path(data, LUKS_UUID, proc, pid_file, tmp_path / "sys")
