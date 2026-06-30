from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/submission_now/models")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates")


def patch(task: str):
    model = onnx.load(BASE / f"{task}.onnx")
    old_output = model.graph.output[0].name
    for node in model.graph.node:
        for idx, out in enumerate(node.output):
            if out == old_output:
                node.output[idx] = "logits"
    model.graph.node.extend(
        [
            helper.make_node("ArgMax", ["logits"], ["labels"], name="labels", axis=1, keepdims=0),
            helper.make_node("OneHot", ["labels", "depth", "onehot_values"], [old_output], name="onehot", axis=1),
        ]
    )
    model.graph.initializer.append(numpy_helper.from_array(np.array(10, dtype=np.int64), name="depth"))
    model.graph.initializer.append(numpy_helper.from_array(np.array([0, 1], dtype=np.float16), name="onehot_values"))
    model.graph.output[0].type.tensor_type.elem_type = TensorProto.FLOAT16
    del model.graph.value_info[:]
    onnx.checker.check_model(model)
    out = OUT / f"{task}_conv_argmax_onehot.onnx"
    onnx.save(model, out)
    print(out)


if __name__ == "__main__":
    for task in ["task099", "task122", "task389"]:
        patch(task)
