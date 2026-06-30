from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task192_equal_output.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    nodes = []
    in_name = "input"

    k2 = np.ones((1, 10, 2, 2), dtype=np.float32)
    k2[:, 0, :, :] = 0.0
    nodes.append(helper.make_node("Conv", [in_name, "k2_nz"], ["sq_count"], name="count_full_2x2"))
    nodes.append(helper.make_node("Greater", ["sq_count", "three_pt_five"], ["sq_good_b"], name="is_full_2x2"))
    nodes.append(helper.make_node("Cast", ["sq_good_b"], ["sq_good_h"], name="full_2x2_to_f16", to=TensorProto.FLOAT16))
    nodes.append(helper.make_node("ConvTranspose", ["sq_good_h", "k2_h"], ["part_count"], name="spread_to_cells"))
    nodes.append(helper.make_node("Greater", ["part_count", "half_h"], ["keep_b"], name="cell_in_full_2x2"))

    nodes.append(helper.make_node("ReduceSum", [in_name, "axes_ch"], ["valid_sum"], name="valid_input_sum", keepdims=1))
    nodes.append(helper.make_node("Greater", ["valid_sum", "zero_f"], ["valid_b"], name="valid_input_cell"))

    nodes.append(helper.make_node("ReduceSum", [in_name, "axes_hw"], ["counts"], name="count_colors", keepdims=1))
    nodes.append(helper.make_node("Slice", ["counts", "starts_c1", "ends_c10", "axes_ch"], ["counts9"], name="drop_background"))
    nodes.append(helper.make_node("ArgMax", ["counts9"], ["arg9"], name="dominant_nonzero_minus1", axis=1, keepdims=1))
    nodes.append(helper.make_node("Add", ["arg9", "one_i64"], ["dom_i64"], name="dominant_nonzero"))
    nodes.append(helper.make_node("Cast", ["dom_i64"], ["dom_u8"], name="dominant_to_u8", to=TensorProto.UINT8))

    nodes.append(helper.make_node("Where", ["keep_b", "dom_u8", "zero_u8"], ["grid_u8_raw"], name="paint_grid"))
    nodes.append(helper.make_node("Where", ["valid_b", "grid_u8_raw", "sentinel_u8"], ["grid_u8"], name="mask_padding"))
    nodes.append(helper.make_node("Equal", ["grid_u8", "colors_u8"], ["output"], name="equal_as_output"))

    graph = helper.make_graph(
        nodes,
        "task192_equal_output",
        [helper.make_tensor_value_info(in_name, TensorProto.FLOAT, [1, 10, 30, 30])],
        [helper.make_tensor_value_info("output", TensorProto.BOOL, [1, 10, 30, 30])],
        [
            init("k2_nz", k2),
            init("k2_h", np.ones((1, 1, 2, 2), dtype=np.float16)),
            init("three_pt_five", np.array(3.5, dtype=np.float32)),
            init("zero_f", np.array(0.0, dtype=np.float32)),
            init("half_h", np.array(0.5, dtype=np.float16)),
            init("axes_ch", np.array([1], dtype=np.int64)),
            init("axes_hw", np.array([2, 3], dtype=np.int64)),
            init("starts_c1", np.array([1], dtype=np.int64)),
            init("ends_c10", np.array([10], dtype=np.int64)),
            init("one_i64", np.array([1], dtype=np.int64).reshape(1, 1, 1, 1)),
            init("zero_u8", np.array([0], dtype=np.uint8).reshape(1, 1, 1, 1)),
            init("sentinel_u8", np.array([255], dtype=np.uint8).reshape(1, 1, 1, 1)),
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
