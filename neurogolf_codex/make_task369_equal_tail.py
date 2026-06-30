from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


SRC = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now/task369.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task369.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    model = onnx.load(SRC)
    graph = model.graph
    drop = {"zeros_4_10_computed_zero_ch", "out10", "output"}
    kept = [n for n in graph.node if n.output[0] not in drop]
    produced = {out for n in kept for out in n.output}
    if not {"ch1_out", "ch2_out", "ch3_out", "ch5__h16"}.issubset(produced):
        raise SystemExit("unexpected source graph shape")
    kept.extend(
        [
            helper.make_node("Mul", ["ch2_out", "two_h"], ["v2"], name="paint2"),
            helper.make_node("Mul", ["ch3_out", "three_h"], ["v3"], name="paint3"),
            helper.make_node("Mul", ["ch5__h16", "five_h"], ["v5"], name="paint5"),
            helper.make_node("Sum", ["ch1_out", "v2", "v3", "v5"], ["grid_crop_h"], name="color_grid_h"),
            helper.make_node("Pad", ["grid_crop_h"], ["grid_h"], name="pad_grid_sentinel", mode="constant", pads=[0, 0, 0, 0, 0, 0, 20, 20], value=255.0),
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
            init("three_h", np.array(3, dtype=np.float16)),
            init("five_h", np.array(5, dtype=np.float16)),
            init("colors_i", np.arange(10, dtype=np.int32).reshape(1, 10, 1, 1)),
        ]
    )
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
