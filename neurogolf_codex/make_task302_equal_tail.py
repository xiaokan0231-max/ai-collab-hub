from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


SRC = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now/task302.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task302.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    model = onnx.load(SRC)
    graph = model.graph
    drop = {"not_paint_b", "out0_b", "zero_b", "out12_b", "output"}
    kept = [n for n in graph.node if n.output[0] not in drop]
    produced = {out for n in kept for out in n.output}
    if not {"c5_b", "bg_b", "is1_b", "is2_b", "is3_b"}.issubset(produced):
        raise SystemExit("unexpected source graph shape")

    kept.extend(
        [
            helper.make_node("Cast", ["c5_b"], ["c5_i"], name="c5_to_i32", to=TensorProto.INT32),
            helper.make_node("Cast", ["is1_b"], ["is1_i"], name="is1_to_i32", to=TensorProto.INT32),
            helper.make_node("Cast", ["is2_b"], ["is2_i"], name="is2_to_i32", to=TensorProto.INT32),
            helper.make_node("Cast", ["is3_b"], ["is3_i"], name="is3_to_i32", to=TensorProto.INT32),
            helper.make_node("Mul", ["c5_i", "five_i"], ["v5"], name="paint5"),
            helper.make_node("Mul", ["is1_i", "six_i"], ["v6"], name="paint6"),
            helper.make_node("Mul", ["is2_i", "seven_i"], ["v7"], name="paint7"),
            helper.make_node("Mul", ["is3_i", "eight_i"], ["v8"], name="paint8"),
            helper.make_node("Add", ["v5", "v6"], ["v56"], name="add_56"),
            helper.make_node("Add", ["v7", "v8"], ["v78"], name="add_78"),
            helper.make_node("Add", ["v56", "v78"], ["grid_crop_raw"], name="color_grid"),
            helper.make_node("Or", ["bg_b", "c5_b"], ["valid_b"], name="valid_cell"),
            helper.make_node("Where", ["valid_b", "grid_crop_raw", "sentinel_i"], ["grid_crop"], name="mask_padding"),
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
            init("five_i", np.array(5, dtype=np.int32)),
            init("six_i", np.array(6, dtype=np.int32)),
            init("seven_i", np.array(7, dtype=np.int32)),
            init("eight_i", np.array(8, dtype=np.int32)),
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
