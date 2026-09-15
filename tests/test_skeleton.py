import inspect

import confluence_md_exporter
import confluence_md_exporter.flow as flow_mod


def test_package_importable() -> None:
    assert confluence_md_exporter.__doc__
    assert confluence_md_exporter.__version__ == "1.0.0"


def test_export_run_has_no_prefect_or_thread_pool() -> None:
    src = inspect.getsource(flow_mod)
    assert "prefect" not in src.lower()
    assert "ThreadPoolExecutor" not in src
