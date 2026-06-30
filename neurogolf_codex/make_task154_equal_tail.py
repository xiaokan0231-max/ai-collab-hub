from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


SRC = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_fresh/task154.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task154.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    model = onnx.load(SRC)
    graph = model.graph
    kept = [n for n in graph.node if n.output[0] not in {"stack3", "output"}]
    produced = {out for n in kept for out in n.output}
    if not {"c2_4d", "c5_out_4d"}.issubset(produced):
        raise SystemExit("unexpected source graph shape")

    kept.extend(
        [
            helper.make_node("Mul", ["c2_4d", "two_h"], ["c2_color_h"], name="color2_grid"),
            helper.make_node("Mul", ["c5_out_4d", "five_h"], ["c5_color_h"], name="color5_grid"),
            helper.make_node("Add", ["c2_color_h", "c5_color_h"], ["grid_raw"], name="color_grid_h"),
            helper.make_node("ReduceSum", ["input"], ["valid_sum"], name="valid_sum", axes=[1], keepdims=1),
            helper.make_node("Greater", ["valid_sum", "zero_f"], ["valid_b"], name="valid_cell"),
            helper.make_node("Where", ["valid_b", "grid_raw", "sentinel_h"], ["grid_h"], name="mask_padding"),
            helper.make_node("Cast", ["grid_h"], ["grid_i"], name="grid_to_i32", to=TensorProto.INT32),
            helper.make_node("Equal", ["grid_i", "colors_i"], ["output"], name="equal_as_output"),
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
            init("zero_f", np.array(0, dtype=np.float32)),
            init("sentinel_h", np.array([255], dtype=np.float16).reshape(1, 1, 1, 1)),
            init("colors_i", np.arange(10, dtype=np.int32).reshape(1, 10, 1, 1)),
        ]
    )
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
