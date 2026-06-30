from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task356_maxpool_span.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def build(use_f16: bool):
    suffix = "_f16" if use_f16 else "_f32"
    out = OUT.with_name(f"task356_maxpool_span{suffix}.onnx")
    nodes = [
        helper.make_node("Slice", ["input", "ch8_st", "ch8_en", "axes4"], ["ch8_f"], name="slice_ch8"),
        helper.make_node("Greater", ["ch8_f", "zero_f"], ["mask8_b"], name="mask8"),
    ]
    pool_in = "ch8_f"
    if use_f16:
        nodes.append(helper.make_node("Cast", ["ch8_f"], ["ch8_h"], name="to_f16", to=TensorProto.FLOAT16))
        pool_in = "ch8_h"
    nodes.extend(
        [
            helper.make_node("MaxPool", [pool_in], ["left_seen_f"], name="left_seen", kernel_shape=[1, 10], pads=[0, 9, 0, 0], strides=[1, 1]),
            helper.make_node("MaxPool", [pool_in], ["right_seen_f"], name="right_seen", kernel_shape=[1, 10], pads=[0, 0, 0, 9], strides=[1, 1]),
            helper.make_node("MaxPool", [pool_in], ["top_seen_f"], name="top_seen", kernel_shape=[10, 1], pads=[9, 0, 0, 0], strides=[1, 1]),
            helper.make_node("MaxPool", [pool_in], ["bottom_seen_f"], name="bottom_seen", kernel_shape=[10, 1], pads=[0, 0, 9, 0], strides=[1, 1]),
            helper.make_node("Cast", ["left_seen_f"], ["left_seen_b"], name="left_bool", to=TensorProto.BOOL),
            helper.make_node("Cast", ["right_seen_f"], ["right_seen_b"], name="right_bool", to=TensorProto.BOOL),
            helper.make_node("Cast", ["top_seen_f"], ["top_seen_b"], name="top_bool", to=TensorProto.BOOL),
            helper.make_node("Cast", ["bottom_seen_f"], ["bottom_seen_b"], name="bottom_bool", to=TensorProto.BOOL),
            helper.make_node("And", ["left_seen_b", "right_seen_b"], ["between_row_b"], name="between_row"),
            helper.make_node("And", ["top_seen_b", "bottom_seen_b"], ["between_col_b"], name="between_col"),
            helper.make_node("Or", ["mask8_b", "between_row_b"], ["row_or_orig_b"], name="row_or_orig"),
            helper.make_node("Or", ["row_or_orig_b", "between_col_b"], ["ch8_out_b"], name="out8"),
            helper.make_node("Not", ["ch8_out_b"], ["ch0_out_b"], name="out0"),
            helper.make_node(
                "Concat",
                ["ch0_out_b", "zero_b", "zero_b", "zero_b", "zero_b", "zero_b", "zero_b", "zero_b", "ch8_out_b", "zero_b"],
                ["output_10"],
                name="concat_out",
                axis=1,
            ),
            helper.make_node("Pad", ["output_10", "pad_to_30", "false_bool"], ["output"], name="pad_out", mode="constant"),
        ]
    )
    graph = helper.make_graph(
        nodes,
        "task356_maxpool_span",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 10, 30, 30])],
        [helper.make_tensor_value_info("output", TensorProto.BOOL, [1, 10, 30, 30])],
        [
            init("ch8_st", np.array([0, 8, 0, 0], dtype=np.int64)),
            init("ch8_en", np.array([1, 9, 10, 10], dtype=np.int64)),
            init("axes4", np.array([0, 1, 2, 3], dtype=np.int64)),
            init("zero_f", np.array(0, dtype=np.float32)),
            init("zero_b", np.zeros((1, 1, 10, 10), dtype=bool)),
            init("false_bool", np.array(False, dtype=bool)),
            init("pad_to_30", np.array([0, 0, 0, 0, 0, 0, 20, 20], dtype=np.int64)),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    out.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, out)
    print(out)


if __name__ == "__main__":
    build(False)
    build(True)
