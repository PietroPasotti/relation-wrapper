import os
from pathlib import Path
from textwrap import dedent

import jinja2 as jinja2

import __version__

root = Path()


def inline_lib():
    py = root / "endpoint_wrapper.py"
    pyi = root / "endpoint_wrapper.pyi"
    template = root / "lib_template.jinja"

    assert py.exists()
    assert pyi.exists()
    assert template.exists()

    lib_file = (
        root
        / "lib"
        / "charms"
        / "relation_wrapper"
        / f"v{__version__.version}"
        / "endpoint_wrapper.py"
    )

    if lib_file.exists() and input("overwrite?") not in "YESyes":
        print("aborting...")
        return

    if not lib_file.parent.exists():
        os.makedirs(lib_file.parent)

    rendered = jinja2.Template(template.read_text()).render(
        {
            "py": py.read_text(),
            "pyi": pyi.read_text(),
            "revision": __version__.revision,
            "version": __version__.version,
        }
    )

    lib_file.write_text(rendered)


if __name__ == "__main__":
    inline_lib()
