import confluence_md_exporter
import prefect


def test_package_importable() -> None:
    assert confluence_md_exporter.__doc__


def test_prefect_v3_installed() -> None:
    major = int(prefect.__version__.split(".")[0])
    assert major == 3
