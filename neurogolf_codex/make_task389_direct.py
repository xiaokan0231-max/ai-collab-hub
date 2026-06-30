from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task389.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    nodes = [
        helper.make_node("ReduceSum", ["input", "axes_hw"], ["counts"], name="count_colors", keepdims=1),
        helper.make_node("Mul", ["counts", "not_five_f"], ["counts_no5"], name="exclude_five"),
        helper.make_node("ArgMax", ["counts_no5"], ["target_i64"], name="target_color", axis=1, keepdims=1),
        helper.make_node("Cast", ["target_i64"], ["target_u8"], name="target_to_u8", to=TensorProto.UINT8),
        helper.make_node("Slice", ["input", "s5", "e5", "axis_ch"], ["c5"], name="get_five_channel"),
        helper.make_node("Cast", ["c5"], ["c5_b"], name="c5_to_bool", to=TensorProto.BOOL),
        helper.make_node("Where", ["c5_b", "target_u8", "zero_u8"], ["grid_raw"], name="paint_fives_as_target"),
        helper.make_node("ReduceSum", ["input", "axis_ch"], ["valid_sum"], name="valid_sum", keepdims=1),
        helper.make_node("Greater", ["valid_sum", "zero_f"], ["valid_b"], name="valid_cells"),
        helper.make_node("Where", ["valid_b", "grid_raw", "sentinel_u8"], ["grid_u8"], name="mask_padding"),
        helper.make_node("Equal", ["grid_u8", "colors_u8"], ["output"], name="equal_as_output"),
    ]

    graph = helper.make_graph(
        nodes,
        "task389_direct",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 10, 30, 30])],
        [helper.make_tensor_value_info("output", TensorProto.BOOL, [1, 10, 30, 30])],
        [
            init("axes_hw", np.array([2, 3], dtype=np.int64)),
            init("axis_ch", np.array([1], dtype=np.int64)),
            init("zero_f", np.array(0, dtype=np.float32)),
            init("not_five_f", np.array([1, 1, 1, 1, 1, 0, 1, 1, 1, 1], dtype=np.float32).reshape(1, 10, 1, 1)),
            init("s5", np.array([5], dtype=np.int64)),
            init("e5", np.array([6], dtype=np.int64)),
            init("zero_u8", np.array(0, dtype=np.uint8)),
            init("sentinel_u8", np.array(255, dtype=np.uint8)),
            init("colors_u8", np.arange(10, dtype=np.uint8).reshape(1, 10, 1, 1)),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 18)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
