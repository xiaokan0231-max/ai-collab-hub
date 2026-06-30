from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task081_conv_corner.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def build(use_f16: bool):
    conv_type = TensorProto.FLOAT16 if use_f16 else TensorProto.FLOAT
    suffix = "_f16" if use_f16 else "_f32"
    out = OUT.with_name(f"task081_conv_corner{suffix}.onnx")

    detect = np.zeros((4, 1, 2, 2), dtype=np.float16 if use_f16 else np.float32)
    detect[0, 0, 0, 1] = 1
    detect[0, 0, 1, 0] = 1
    detect[0, 0, 1, 1] = 1
    detect[1, 0, 0, 0] = 1
    detect[1, 0, 1, 0] = 1
    detect[1, 0, 1, 1] = 1
    detect[2, 0, 0, 0] = 1
    detect[2, 0, 0, 1] = 1
    detect[2, 0, 1, 1] = 1
    detect[3, 0, 0, 0] = 1
    detect[3, 0, 0, 1] = 1
    detect[3, 0, 1, 0] = 1

    place = np.zeros((4, 1, 2, 2), dtype=np.float16 if use_f16 else np.float32)
    place[0, 0, 0, 0] = 1
    place[1, 0, 0, 1] = 1
    place[2, 0, 1, 0] = 1
    place[3, 0, 1, 1] = 1

    nodes = [
        helper.make_node("Slice", ["input", "c8_start", "c8_end", "axes4"], ["c8_f"], name="slice_c8"),
        helper.make_node("Greater", ["c8_f", "zero_f"], ["m8"], name="mask8"),
    ]
    conv_in = "c8_f"
    if use_f16:
        nodes.append(helper.make_node("Cast", ["c8_f"], ["c8_h"], name="to_f16", to=TensorProto.FLOAT16))
        conv_in = "c8_h"
    nodes.extend(
        [
            helper.make_node("Conv", [conv_in, "detect_k"], ["hit_score"], name="detect_three", kernel_shape=[2, 2]),
            helper.make_node("Greater", ["hit_score", "thr"], ["hit_b"], name="is_three"),
            helper.make_node("Cast", ["hit_b"], ["hit_num"], name="hit_to_num", to=conv_type),
            helper.make_node("ConvTranspose", ["hit_num", "place_k"], ["mark_score"], name="place_missing", kernel_shape=[2, 2]),
            helper.make_node("Greater", ["mark_score", "zero_num"], ["mark_raw"], name="mark_positive"),
            helper.make_node("Not", ["m8"], ["not8"], name="not8"),
            helper.make_node("And", ["mark_raw", "not8"], ["mark1"], name="new_ones"),
            helper.make_node("Or", ["m8", "mark1"], ["fg_any"], name="fg_any"),
            helper.make_node("Not", ["fg_any"], ["bg"], name="bg"),
            helper.make_node(
                "Concat",
                ["bg", "mark1", "zero_chan", "zero_chan", "zero_chan", "zero_chan", "zero_chan", "zero_chan", "m8", "zero_chan"],
                ["out7"],
                name="concat_out",
                axis=1,
            ),
            helper.make_node("Pad", ["out7", "pad_to_30", "false_bool"], ["output"], name="pad_out", mode="constant"),
        ]
    )

    graph = helper.make_graph(
        nodes,
        "task081_conv_corner",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 10, 30, 30])],
        [helper.make_tensor_value_info("output", TensorProto.BOOL, [1, 10, 30, 30])],
        [
            init("c8_start", np.array([0, 8, 0, 0], dtype=np.int64)),
            init("c8_end", np.array([1, 9, 7, 7], dtype=np.int64)),
            init("axes4", np.array([0, 1, 2, 3], dtype=np.int64)),
            init("zero_f", np.array(0, dtype=np.float32)),
            init("zero_num", np.array(0, dtype=np.float16 if use_f16 else np.float32)),
            init("thr", np.array(2.5, dtype=np.float16 if use_f16 else np.float32)),
            init("detect_k", detect),
            init("place_k", place),
            init("zero_chan", np.zeros((1, 1, 7, 7), dtype=bool)),
            init("false_bool", np.array(False, dtype=bool)),
            init("pad_to_30", np.array([0, 0, 0, 0, 0, 0, 23, 23], dtype=np.int64)),
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
