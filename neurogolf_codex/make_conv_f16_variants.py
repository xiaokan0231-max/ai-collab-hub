from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/submission_now/models")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates")


def patch(task: str):
    model = onnx.load(BASE / f"{task}.onnx")
    for i, initializer in enumerate(model.graph.initializer):
        arr = numpy_helper.to_array(initializer)
        if arr.dtype == np.float32:
            model.graph.initializer[i].CopyFrom(numpy_helper.from_array(arr.astype(np.float16), name=initializer.name))
    first_inputs = set(model.graph.node[0].input)
    if "input" in first_inputs:
        model.graph.node.insert(0, helper.make_node("Cast", ["input"], ["input_h"], name="input_to_f16", to=TensorProto.FLOAT16))
        for node in model.graph.node[1:]:
            for idx, name in enumerate(node.input):
                if name == "input":
                    node.input[idx] = "input_h"
    del model.graph.value_info[:]
    for output in model.graph.output:
        output.type.tensor_type.elem_type = TensorProto.FLOAT16
    onnx.checker.check_model(model)
    out = OUT / f"{task}_conv_f16.onnx"
    onnx.save(model, out)
    print(out)


if __name__ == "__main__":
    for task in ["task099", "task122", "task389"]:
        patch(task)
