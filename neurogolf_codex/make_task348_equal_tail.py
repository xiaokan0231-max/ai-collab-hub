from pathlib import Path

import numpy as np
import onnx
from onnx import helper, numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now/task348.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task348_equal_tail.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    model = onnx.load(BASE)
    keep = []
    for node in model.graph.node:
        if node.output and node.output[0] in {"not_colored_b", "ch0_b", "output_10", "output"}:
            continue
        keep.append(node)
    del model.graph.node[:]
    model.graph.node.extend(keep)
    model.graph.node.extend(
        [
            helper.make_node("Where", ["ch7_b", "seven_u8", "zero_u8"], ["grid7"], name="grid7"),
            helper.make_node("Where", ["ch8_b", "eight_u8", "grid7"], ["grid_raw"], name="grid8"),
            helper.make_node("Where", ["in_grid_b", "grid_raw", "sentinel_u8"], ["grid_u8"], name="mask_invalid"),
            helper.make_node("Equal", ["grid_u8", "colors_u8"], ["inner"], name="equal_inner"),
            helper.make_node("Pad", ["inner", "pad_to_30", "false_bool"], ["output"], name="pad_out", mode="constant"),
        ]
    )
    used = {i.name for i in model.graph.initializer}
    for name, arr in [
        ("zero_u8", np.array(0, dtype=np.uint8)),
        ("seven_u8", np.array(7, dtype=np.uint8)),
        ("eight_u8", np.array(8, dtype=np.uint8)),
        ("sentinel_u8", np.array(255, dtype=np.uint8)),
        ("colors_u8", np.arange(10, dtype=np.uint8).reshape(1, 10, 1, 1)),
        ("false_bool", np.array(False, dtype=bool)),
    ]:
        if name not in used:
            model.graph.initializer.append(init(name, arr))
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
