from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/submission_now/models/task273.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task273_f16.onnx")


def main():
    model = onnx.load(BASE)
    for i, initializer in enumerate(model.graph.initializer):
        arr = numpy_helper.to_array(initializer)
        if arr.dtype == np.float32:
            model.graph.initializer[i].CopyFrom(numpy_helper.from_array(arr.astype(np.float16), name=initializer.name))
    new_nodes = []
    for node in model.graph.node:
        new_nodes.append(node)
        if node.op_type == "Slice" and node.output and node.output[0] == "ch4":
            node.output[0] = "ch4_raw"
            new_nodes.append(helper.make_node("Cast", ["ch4_raw"], ["ch4"], name="ch4_to_f16", to=TensorProto.FLOAT16))
    del model.graph.node[:]
    model.graph.node.extend(new_nodes)
    del model.graph.value_info[:]
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
