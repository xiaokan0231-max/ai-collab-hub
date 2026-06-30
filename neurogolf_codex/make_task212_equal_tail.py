from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


SRC = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_fresh/task212.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task212.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    model = onnx.load(SRC)
    graph = model.graph
    drop = {"any_color_sum_2", "any_color_gt", "any_color_clip", "bg", "out10", "output"}
    kept = [n for n in graph.node if n.output[0] not in drop]
    produced = {out for n in kept for out in n.output}
    if not {"out1_clip", "out2_clip", "c5__h16"}.issubset(produced):
        raise SystemExit("unexpected source graph shape")

    kept.extend(
        [
            helper.make_node("Mul", ["out2_clip", "two_h"], ["out2_color"], name="out2_color"),
            helper.make_node("Mul", ["c5__h16", "five_h"], ["c5_color"], name="c5_color"),
            helper.make_node("Sum", ["out1_clip", "out2_color", "c5_color"], ["grid10"], name="color_grid"),
            helper.make_node("Pad", ["grid10", "pad_grid_to_30", "sentinel_h"], ["grid30"], name="pad_grid_sentinel"),
            helper.make_node("Equal", ["grid30", "colors_h"], ["output"], name="equal_as_output"),
        ]
    )
    del graph.node[:]
    graph.node.extend(kept)
    del graph.output[:]
    graph.output.extend([helper.make_tensor_value_info("output", TensorProto.BOOL, [1, 10, 30, 30])])
    graph.initializer.extend(
        [
            init("two_h", np.array(2, dtype=np.float16)),
            init("five_h", np.array(5, dtype=np.float16)),
            init("pad_grid_to_30", np.array([0, 0, 0, 0, 0, 0, 20, 20], dtype=np.int64)),
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
