from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/submission_now/models/task040.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task040_f16.onnx")


def main():
    model = onnx.load(BASE)
    for i, initializer in enumerate(model.graph.initializer):
        arr = numpy_helper.to_array(initializer)
        if arr.dtype == np.float32:
            model.graph.initializer[i].CopyFrom(numpy_helper.from_array(arr.astype(np.float16), name=initializer.name))
    for node in model.graph.node:
        if node.op_type == "Cast" and node.output and node.output[0] == "encoded_10":
            for attr in node.attribute:
                if attr.name == "to":
                    attr.i = TensorProto.FLOAT16
    del model.graph.value_info[:]
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
