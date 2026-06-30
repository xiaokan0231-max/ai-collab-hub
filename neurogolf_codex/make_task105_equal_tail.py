from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


SRC = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_fresh/task105.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task105.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    model = onnx.load(SRC)
    graph = model.graph
    drop = {"not_two_mask_b", "out0_b", "zero_b", "out_crop_b", "output"}
    kept = [n for n in graph.node if n.output[0] not in drop]
    produced = {out for n in kept for out in n.output}
    if not {"two_mask_b", "ones_b", "ch0_b"}.issubset(produced):
        raise SystemExit("unexpected source graph shape")

    kept.extend(
        [
            helper.make_node("Cast", ["ones_b"], ["ones_i"], name="ones_to_i32", to=TensorProto.INT32),
            helper.make_node("Where", ["two_mask_b", "two_i", "ones_i"], ["grid_raw"], name="paint_twos"),
            helper.make_node("Or", ["ch0_b", "ones_b"], ["valid_b"], name="valid_cell"),
            helper.make_node("Where", ["valid_b", "grid_raw", "sentinel_i"], ["grid_crop"], name="mask_padding"),
            helper.make_node("Pad", ["grid_crop", "pad_to_30", "sentinel_i"], ["grid_i"], name="pad_grid_sentinel"),
            helper.make_node("Equal", ["grid_i", "colors_i"], ["output"], name="equal_as_output"),
        ]
    )
    del graph.node[:]
    graph.node.extend(kept)
    del graph.output[:]
    graph.output.extend([helper.make_tensor_value_info("output", TensorProto.BOOL, [1, 10, 30, 30])])
    graph.initializer.extend(
        [
            init("two_i", np.array(2, dtype=np.int32)),
            init("sentinel_i", np.array(255, dtype=np.int32)),
            init("colors_i", np.arange(10, dtype=np.int32).reshape(1, 10, 1, 1)),
        ]
    )
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
