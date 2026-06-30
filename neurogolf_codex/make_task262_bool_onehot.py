from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now/task262.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task262_bool_onehot.onnx")


def main():
    model = onnx.load(BASE)
    for i, initializer in enumerate(model.graph.initializer):
        if initializer.name == "onehot_values":
            model.graph.initializer[i].CopyFrom(numpy_helper.from_array(np.array([False, True], dtype=bool), name="onehot_values"))
            break
    for out in model.graph.output:
        if out.name == "output":
            out.type.tensor_type.elem_type = TensorProto.BOOL
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
