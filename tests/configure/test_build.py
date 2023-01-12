import io
from pathlib import Path
from unittest import mock

from vulchecker.configure import vulcheckerConfig
from vulchecker.configure.base import SourceFile


def test_build_ninja_file(tmp_path):
    with mock.patch(
        "importlib.import_module",
        autospec=True,
        return_value=mock.NonCallableMock(
            get_sources=mock.Mock(
                return_value=[
                    SourceFile(tmp_path / "foo.c"),
                    SourceFile(tmp_path / "bar.c"),
                ]
            ),
            get_reconfigure_inputs=mock.Mock(return_value=[]),
        ),
    ), mock.patch("vulchecker.configure.Writer", autospec=True) as writer_cls_mock:
        (tmp_path / "vulchecker").mkdir()
        vulcheckerConfig(
            tmp_path,
            tmp_path,
            tmp_path / "vulchecker",
            Path("/usr/lib"),
            "dummy",
            "foo",
            [0],
            None,
        ).build_ninja_file()

        writer_mock = writer_cls_mock(None)
        assert writer_mock.build.mock_calls == [
            mock.call(
                ["foo.ll"],
                "analyze_source",
                ["../foo.c"],
                variables={"extra_flags": []},
            ),
            mock.call(
                ["bar.ll"],
                "analyze_source",
                ["../bar.c"],
                variables={"extra_flags": []},
            ),
            mock.call(["foo-combine_ll.ll"], "combine_ll", ["foo.ll", "bar.ll"]),
            mock.call(
                ["foo-allow_optimization.ll"],
                "allow_optimization",
                ["foo-combine_ll.ll"],
            ),
            mock.call(
                ["foo-opt_indirectbr.ll"],
                "opt_indirectbr",
                ["foo-allow_optimization.ll"],
            ),
            mock.call(
                ["foo-opt_globaldce.ll"], "opt_globaldce", ["foo-opt_indirectbr.ll"]
            ),
            mock.call(
                ["vulchecker-0.json"],
                "opt_llap",
                ["foo-opt_globaldce.ll"],
                implicit=["$llap_path/LLVM_vulchecker_0.so"],
                variables={"llap_plugin": 0},
            ),
            mock.call(["vulchecker.ninja"], "reconfigure_vulchecker", []),
        ]


def test_vulchecker_config_round_trip():
    vulchecker_config = vulcheckerConfig(
        source_dir="/foo",
        build_dir="/bar",
        vulchecker_dir="/baz",
        llap_lib_dir="/qux",
        build_system="dummy",
        target="default",
        cwes=[0],
    )
    f = io.StringIO()
    vulchecker_config._to_ninja_file(f)
    f.seek(0)
    new_config = vulcheckerConfig._from_ninja_file(f)
    assert new_config == vulchecker_config
