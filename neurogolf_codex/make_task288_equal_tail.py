from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


SRC = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_fresh/task288.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task288.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    model = onnx.load(SRC)
    graph = model.graph
    drop = {"new_colors", "any_color", "new_bg", "out9", "output"}
    kept = [n for n in graph.node if n.output[0] not in drop]
    produced = {out for n in kept for out in n.output}
    if not {"new_colors_bool", "active"}.issubset(produced):
        raise SystemExit("unexpected source graph shape")

    kept.extend(
        [
            helper.make_node("Cast", ["new_colors_bool"], ["new_colors_h"], name="new_colors_to_h", to=TensorProto.FLOAT16),
            helper.make_node("Mul", ["new_colors_h", "vals9_h"], ["weighted_colors"], name="weighted_colors"),
            helper.make_node("ReduceSum", ["weighted_colors", "axis_ch"], ["grid_raw"], name="grid_from_channels", keepdims=1),
            helper.make_node("Greater", ["active", "zero"], ["valid_b"], name="valid_cell"),
            helper.make_node("Where", ["valid_b", "grid_raw", "sentinel_h"], ["grid9"], name="mask_crop_padding"),
            helper.make_node("Pad", ["grid9", "pad_to_30", "sentinel_h"], ["grid30"], name="pad_grid_sentinel"),
            helper.make_node("Equal", ["grid30", "colors_h"], ["output"], name="equal_as_output"),
        ]
    )
    del graph.node[:]
    graph.node.extend(kept)
    del graph.output[:]
    graph.output.extend([helper.make_tensor_value_info("output", TensorProto.BOOL, [1, 10, 30, 30])])
    graph.initializer.extend(
        [
            init("vals9_h", np.arange(1, 10, dtype=np.float16).reshape(1, 9, 1, 1)),
            init("axis_ch", np.array([1], dtype=np.int64)),
            init("sentinel_h", np.array(255, dtype=np.float16)),
            init("colors_h", np.arange(10, dtype=np.float16).reshape(1, 10, 1, 1)),
        ]
    )
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
