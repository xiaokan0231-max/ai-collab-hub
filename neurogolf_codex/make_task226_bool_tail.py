from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/submission_now/models/task226.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task226_bool_tail.onnx")


def main():
    model = onnx.load(BASE)
    keep = []
    for node in model.graph.node:
        if node.output and node.output[0] in {"fill_any_clip", "bg_out", "out10", "output"}:
            continue
        keep.append(node)
    keep.extend(
        [
            helper.make_node("Cast", ["bg__h16"], ["bg_b0"], name="bg_bool0", to=TensorProto.BOOL),
            helper.make_node("Not", ["fill_any_gt"], ["not_fill_b"], name="not_fill"),
            helper.make_node("And", ["bg_b0", "not_fill_b"], ["bg_b"], name="bg_bool"),
            helper.make_node("Cast", ["fill1"], ["fill1_b"], name="fill1_bool", to=TensorProto.BOOL),
            helper.make_node("Cast", ["fill2"], ["fill2_b"], name="fill2_bool", to=TensorProto.BOOL),
            helper.make_node("Cast", ["fill3"], ["fill3_b"], name="fill3_bool", to=TensorProto.BOOL),
            helper.make_node("Cast", ["c5__h16"], ["c5_b"], name="c5_bool", to=TensorProto.BOOL),
            helper.make_node(
                "Concat",
                ["bg_b", "fill1_b", "fill2_b", "fill3_b", "zero_b", "c5_b"],
                ["out6_b"],
                name="concat_bool",
                axis=1,
            ),
            helper.make_node("Pad", ["out6_b", "pad_to_30_channelpad", "false_bool"], ["output"], name="pad_bool", mode="constant"),
        ]
    )
    del model.graph.node[:]
    model.graph.node.extend(keep)
    names = {i.name for i in model.graph.initializer}
    if "zero_b" not in names:
        model.graph.initializer.append(numpy_helper.from_array(np.zeros((1, 1, 10, 10), dtype=bool), name="zero_b"))
    if "false_bool" not in names:
        model.graph.initializer.append(numpy_helper.from_array(np.array(False, dtype=bool), name="false_bool"))
    model.graph.output[0].type.tensor_type.elem_type = TensorProto.BOOL
    del model.graph.value_info[:]
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
