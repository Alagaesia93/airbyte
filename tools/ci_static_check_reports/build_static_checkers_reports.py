#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#
import sys
from invoke import Context

from tasks import _run_task


CHECKERS = [
    "black",
    "coverage",
    "flake",
    "isort",
    "mypy",
    "test",
]


def build_static_checkers_reports(modules):
    ctx = Context()
    for module_path in modules:
        for checker in CHECKERS:
            _run_task(ctx, module_path, checker, multi_envs=False)


if __name__ == "__main__":
    print("Changed modules: ", sys.argv[1:])
    build_static_checkers_reports(sys.argv[1:])
