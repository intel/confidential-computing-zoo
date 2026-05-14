"""Image registry reference helpers."""

from ..config import DOCKER_REGISTRY, DOCKER_REPOSITORY


def canonical_registry_ref(image_name: str) -> str:
    """Build the canonical registry reference for *image_name*.

    The format mirrors what ``cosign sign`` / ``cosign attest`` / launch
    verification all expect::

        <DOCKER_REGISTRY>/<DOCKER_REPOSITORY>/<base>:latest-encrypted

    For local registries (``localhost:`` / ``127.0.0.1:``), the top-level
    ``DOCKER_REGISTRY`` is omitted because ``DOCKER_REPOSITORY`` already
    includes the host.
    """
    base_name = image_name.split("/")[-1] + ":latest-encrypted"
    if DOCKER_REPOSITORY.startswith(("localhost:", "127.0.0.1:")):
        return f"{DOCKER_REPOSITORY}/{base_name}"
    return f"{DOCKER_REGISTRY}/{DOCKER_REPOSITORY}/{base_name}"
