from pathlib import Path

import numpy as np
import onnx
from onnx import numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates")


def patch(task: str, hw: int):
    model = onnx.load(BASE / f"{task}.onnx")
    nodes = []
    removed = False
    for node in model.graph.node:
        if node.output and node.output[0] == "zero_b" and node.op_type == "And":
            removed = True
            continue
        nodes.append(node)
    if not removed:
        raise RuntimeError(f"{task}: zero_b And not found")
    del model.graph.node[:]
    model.graph.node.extend(nodes)
    model.graph.initializer.append(numpy_helper.from_array(np.zeros((1, 1, hw, hw), dtype=bool), name="zero_b"))
    onnx.checker.check_model(model)
    out = OUT / f"{task}_zero_const.onnx"
    onnx.save(model, out)
    print(out)


if __name__ == "__main__":
    patch("task136", 10)
    patch("task160", 10)
