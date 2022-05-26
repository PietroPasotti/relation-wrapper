import os
import re
import sys
import traceback
from pathlib import Path
from subprocess import PIPE, Popen
from typing import List, Tuple

import pytest

occurred_fail = re.compile(r":(?P<line>\d*):\d* - error: (?P<error>.*)")
expected_fail = re.compile(r"(?P<line>\d*):.*# pyright: expect-error(?P<reason> .*)?")
revealed_type = re.compile(
    r''':(?P<line>\d*):\d* - information: Type of \".*\" is \"(?P<revealed_type>.*)\"'''
)
expected_type = re.compile(r"(?P<line>\d*):.*# pyright: expect-type(?P<type> .*)?")


class PyrightTestError(RuntimeError):
    def __init__(self, failures: List[Tuple[int, str]]):
        self.failures = failures


def _pyright_test(path, cwd):
    # warning: for this to work properly, the cwd should be the project root.
    # if there are unexpected false positive/negatives, this might be the reason

    file = Path(path)
    proc = Popen(["pyright", str(file)], stdout=PIPE, env=os.environ, cwd=cwd)
    proc.wait()
    out = proc.stdout.read().decode("utf-8")  # type: ignore
    source_lines = file.read_text().split("\n")
    numbered_source = "\n".join(f"{i}:" + line for i, line in enumerate(source_lines))

    _check_types(numbered_source, out)
    _check_revealed_types(numbered_source, out)


def _parse(numbered_source, output, source_re, output_re):
    out_matches = output_re.findall(output)
    exp_matches = source_re.findall(numbered_source)

    # line numbering is base 1 for pyright
    occurred_map = {int(line): reason.strip() for line, reason in out_matches}
    expected_map = {int(line) + 1: reason.strip() for line, reason in exp_matches}
    return occurred_map, expected_map


def _check_revealed_types(numbered_source, out):
    revealed_type_map, expected_type_map = _parse(
        numbered_source, out, expected_type, revealed_type
    )

    failures = []
    for line, expected_type_ in expected_type_map.items():
        rev_type = revealed_type_map.get(line)
        if not rev_type:
            failures.append(
                (line, f"Expected type: {expected_type_!r}, but none was revealed.")
            )
        elif rev_type != expected_type_:
            failures.append(
                (line, f"Expected: {expected_type_!r}, Revealed: {rev_type!r}.")
            )

    _raise_if_any(failures)


def _check_types(numbered_source, out):
    occurred_error_map, expected_error_map = _parse(
        numbered_source, out, expected_fail, occurred_fail
    )

    failures = []

    for line, reason in occurred_error_map.items():
        # check that all errors are expected
        if line not in expected_error_map:
            failures.append((line, f"Unexpected failure: {reason!r}"))
        elif (expected_reason := expected_error_map[line]) != "":
            if expected_reason != reason:
                failures.append(
                    (line, f"Expected failure for {expected_reason!r}; got {reason!r}")
                )

    for line, expected_reason in expected_error_map.items():
        # check that all expected errors have occurred
        if line not in occurred_error_map:
            failures.append((line, f"Did not fail: {expected_reason!r}"))

    _raise_if_any(failures)


def _raise_if_any(failures: List[Tuple[int, str]]):
    if failures:
        raise PyrightTestError(failures)


def pyright_test(path, cwd):
    # todo prettify test output, the stack trace is ugly
    _pyright_test(path, cwd)
