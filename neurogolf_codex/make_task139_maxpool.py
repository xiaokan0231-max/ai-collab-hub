from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task139.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def build(use_f16: bool):
    suffix = "_f16" if use_f16 else "_f32"
    out = OUT.with_name(f"task139_maxpool{suffix}.onnx")
    nodes = [
        helper.make_node("Slice", ["input", "c4_start", "c4_end", "axes4"], ["c4_f"], name="slice_c4"),
        helper.make_node("Greater", ["c4_f", "zero_f"], ["m4"], name="mask4"),
    ]
    pool_in = "c4_f"
    if use_f16:
        nodes.append(helper.make_node("Cast", ["c4_f"], ["c4_h"], name="to_f16", to=TensorProto.FLOAT16))
        pool_in = "c4_h"
    nodes.extend(
        [
            helper.make_node("MaxPool", [pool_in], ["row_near_f"], name="row_near", kernel_shape=[1, 5], pads=[0, 2, 0, 2], strides=[1, 1]),
            helper.make_node("MaxPool", [pool_in], ["col_near_f"], name="col_near", kernel_shape=[5, 1], pads=[2, 0, 2, 0], strides=[1, 1]),
            helper.make_node("Cast", ["row_near_f"], ["row_has"], name="row_to_bool", to=TensorProto.BOOL),
            helper.make_node("Cast", ["col_near_f"], ["col_has"], name="col_to_bool", to=TensorProto.BOOL),
            helper.make_node("And", ["row_has", "col_has"], ["inside_box"], name="inside_box"),
            helper.make_node("Not", ["m4"], ["not4"], name="not4"),
            helper.make_node("And", ["inside_box", "not4"], ["mark7"], name="mark7"),
            helper.make_node("Or", ["m4", "mark7"], ["fg_any"], name="fg_any"),
            helper.make_node("Not", ["fg_any"], ["bg"], name="bg"),
            helper.make_node(
                "Concat",
                ["bg", "zero_chan", "zero_chan", "zero_chan", "m4", "zero_chan", "zero_chan", "mark7", "zero_chan", "zero_chan"],
                ["out9"],
                name="concat_out",
                axis=1,
            ),
            helper.make_node("Pad", ["out9", "pad_to_30", "false_bool"], ["output"], name="pad_out", mode="constant"),
        ]
    )
    graph = helper.make_graph(
        nodes,
        "task139_maxpool",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 10, 30, 30])],
        [helper.make_tensor_value_info("output", TensorProto.BOOL, [1, 10, 30, 30])],
        [
            init("c4_start", np.array([0, 4, 0, 0], dtype=np.int64)),
            init("c4_end", np.array([1, 5, 9, 9], dtype=np.int64)),
            init("axes4", np.array([0, 1, 2, 3], dtype=np.int64)),
            init("zero_f", np.array(0, dtype=np.float32)),
            init("zero_chan", np.zeros((1, 1, 9, 9), dtype=bool)),
            init("false_bool", np.array(False, dtype=bool)),
            init("pad_to_30", np.array([0, 0, 0, 0, 0, 0, 21, 21], dtype=np.int64)),
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
