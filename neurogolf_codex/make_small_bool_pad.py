from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/submission_now/models")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates")


def patch(task: str, pad_input: str):
    model = onnx.load(BASE / f"{task}.onnx")
    new_nodes = []
    for node in model.graph.node:
        if node.op_type == "Pad" and node.output and node.output[0] == "output":
            new_nodes.append(helper.make_node("Cast", [pad_input], [pad_input + "_b"], name="to_bool_before_pad", to=TensorProto.BOOL))
            del node.input[:]
            node.input.extend([pad_input + "_b", "pads_c", "false_bool"])
        new_nodes.append(node)
    del model.graph.node[:]
    model.graph.node.extend(new_nodes)
    if not any(i.name == "false_bool" for i in model.graph.initializer):
        model.graph.initializer.append(numpy_helper.from_array(np.array(False, dtype=bool), name="false_bool"))
    model.graph.output[0].type.tensor_type.elem_type = TensorProto.BOOL
    del model.graph.value_info[:]
    onnx.checker.check_model(model)
    out = OUT / f"{task}_bool_pad.onnx"
    onnx.save(model, out)
    print(out)


if __name__ == "__main__":
    patch("task052", "combined")
    patch("task229", "combined_c")
