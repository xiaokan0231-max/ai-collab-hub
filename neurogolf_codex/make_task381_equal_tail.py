from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now/task381.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task381_equal_tail.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    model = onnx.load(BASE)
    keep = []
    for node in model.graph.node:
        if node.name in {"or_either", "not_bg", "concat_inner", "pad_output"}:
            continue
        keep.append(node)
    del model.graph.node[:]
    model.graph.node.extend(keep)
    model.graph.node.extend(
        [
            helper.make_node("Where", ["is_red", "two_u8", "zero_u8"], ["grid_red"], name="grid_red"),
            helper.make_node("Where", ["maroon", "nine_u8", "grid_red"], ["grid_u8"], name="grid_maroon"),
            helper.make_node("Equal", ["grid_u8", "colors_u8"], ["inner"], name="equal_inner"),
            helper.make_node("Pad", ["inner", "out_pads", "false_bool"], ["output"], name="pad_output", mode="constant"),
        ]
    )
    old = {i.name for i in model.graph.initializer}
    for name, arr in [
        ("two_u8", np.array(2, dtype=np.uint8)),
        ("nine_u8", np.array(9, dtype=np.uint8)),
        ("zero_u8", np.array(0, dtype=np.uint8)),
        ("colors_u8", np.arange(10, dtype=np.uint8).reshape(1, 10, 1, 1)),
        ("false_bool", np.array(False, dtype=bool)),
    ]:
        if name not in old:
            model.graph.initializer.append(init(name, arr))
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
