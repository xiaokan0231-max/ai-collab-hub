import argparse
import contextlib
import io
import os
import re
import sys

import onnx


RAW = "/Users/kanxiao/IdeaProjects/kaggletest/neurogolf/data/raw"
sys.path.insert(0, f"{RAW}/neurogolf_utils")
import neurogolf_utils as ng  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()

    task_num = int(re.search(r"(\d+)$", args.task).group(1))
    ng._NEUROGOLF_DIR = RAW + os.sep
    model = onnx.load(args.model)
    scratch = f"/tmp/ng_hub_verify_{task_num:03d}"
    os.makedirs(scratch, exist_ok=True)
    cwd = os.getcwd()
    os.chdir(scratch)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ng.verify_network(model, task_num, ng.load_examples(task_num))
        output = buf.getvalue()
    finally:
        os.chdir(cwd)
    print(output)
    if "IS READY" not in output:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
