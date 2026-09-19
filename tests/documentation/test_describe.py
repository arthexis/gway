import pytest
import inspect
from types import ModuleType

from gway.documentation import describe
from gway.ingestion.python import ingest_module


def test_describe_raw_callable_uses_signature_and_optional_args_prose():
    def deploy(target: str, force=False, retries: int = 3):
        """Deploy one target.

        Args:
            target: Deployment target name or address.
            force: Replace an existing deployment even when it differs.
        """

    documentation = describe(deploy)

    assert documentation.callable is deploy
    assert documentation.target is deploy
    assert documentation.summary == "Deploy one target."
    assert documentation.signature == inspect.signature(deploy)
    assert documentation.parameter("target").required is True
    assert documentation.parameter("target").annotation is str
    assert (
        documentation.parameter("target").description
        == "Deployment target name or address."
    )
    assert documentation.parameter("force").default is False
    assert (
        documentation.parameter("force").description
        == "Replace an existing deployment even when it differs."
    )
    assert documentation.parameter("retries").annotation is int
    assert documentation.parameter("retries").description is None


def test_describe_tolerates_missing_docstring_and_annotations():
    def ping(host, timeout=5):
        pass

    documentation = describe(ping)

    assert documentation.summary == ""
    assert documentation.docstring == ""
    assert documentation.parameter("host").required is True
    assert documentation.parameter("host").annotation is inspect.Parameter.empty
    assert documentation.parameter("timeout").default == 5
    assert documentation.parameter("timeout").description is None


def test_args_parser_accepts_multiline_and_typed_entries():
    def connect(host, token=None):
        """Connect to a service.

        Parameters:
            host (str): Hostname or IP address of the remote service.
                A port may be included when the transport supports it.
            token: Optional authentication token.
        """

    documentation = describe(connect)

    assert documentation.parameter("host").description == (
        "Hostname or IP address of the remote service. "
        "A port may be included when the transport supports it."
    )
    assert documentation.parameter("token").description == (
        "Optional authentication token."
    )


def test_describe_bound_gway_operation_prefers_existing_provenance(gateway):
    module = ModuleType("demo")

    def connect(host: str, timeout=5):
        """Connect to a remote endpoint.

        Args:
            host: Remote hostname or address.
        """

    module.connect = connect
    ingest_module(gateway, module, path=("demo",))
    bound = gateway.ops.resolve("demo.connect")

    documentation = describe(bound)

    assert documentation.callable is bound
    assert documentation.target is connect
    assert documentation.source is module
    assert documentation.source_kind == "python"
    assert documentation.path == ("demo", "connect")
    assert documentation.operation == "demo.connect"
    assert documentation.subject == "demo"
    assert documentation.signature == inspect.signature(connect)
    assert documentation.parameter("host").description == (
        "Remote hostname or address."
    )


def test_describe_respects_receiver_adjusted_bound_signature(gateway):
    class Device:
        def label(self, prefix: str):
            """Return a device label.

            Args:
                prefix: Text placed before the device identifier.
            """

    gateway.ingest(Device, path=("device",))
    bound = gateway.ops.resolve("device.label")
    documentation = describe(bound)

    assert list(documentation.signature.parameters) == ["prefix"]
    assert documentation.parameter("prefix").required is True
    assert documentation.parameter("prefix").description == (
        "Text placed before the device identifier."
    )
    assert documentation.metadata["receiver"] == "device"


def test_describe_rejects_non_callable():
    with pytest.raises(TypeError, match="documentation target must be callable"):
        describe(42)


def test_parameter_prose_is_optional_and_does_not_override_signature_facts():
    def reconcile(source: str, upgrade=True, force=False):
        """Reconcile one managed project.

        Args:
            force: Allow replacement of a dirty managed installation.
        """

    documentation = describe(reconcile)

    source = documentation.parameter("source")
    upgrade = documentation.parameter("upgrade")
    force = documentation.parameter("force")

    assert source.description is None
    assert source.required is True
    assert source.annotation is str

    assert upgrade.description is None
    assert upgrade.required is False
    assert upgrade.default is True

    assert force.description == (
        "Allow replacement of a dirty managed installation."
    )
    assert force.required is False
    assert force.default is False
