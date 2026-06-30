from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/submission_now/models/task288.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task288_bool_tail.onnx")


def main():
    model = onnx.load(BASE)
    keep = []
    for node in model.graph.node:
        if node.output and node.output[0] in {"new_bg", "out9", "output"}:
            continue
        keep.append(node)
    keep.extend(
        [
            helper.make_node("Cast", ["any_color"], ["any_color_b"], name="any_color_to_bool", to=TensorProto.BOOL),
            helper.make_node("Not", ["any_color_b"], ["not_color_b"], name="not_color"),
            helper.make_node("Cast", ["active"], ["active_b"], name="active_to_bool", to=TensorProto.BOOL),
            helper.make_node("And", ["not_color_b", "active_b"], ["new_bg_b"], name="new_bg_bool"),
            helper.make_node("Concat", ["new_bg_b", "new_colors_bool"], ["out9_b"], name="concat_bool", axis=1),
            helper.make_node("Pad", ["out9_b", "pad_to_30", "false_bool"], ["output"], name="pad_bool", mode="constant"),
        ]
    )
    del model.graph.node[:]
    model.graph.node.extend(keep)
    model.graph.initializer.append(numpy_helper.from_array(np.array(False, dtype=bool), name="false_bool"))
    model.graph.output[0].type.tensor_type.elem_type = TensorProto.BOOL
    del model.graph.value_info[:]
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
