from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


SRC = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_fresh/task206.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task206.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    model = onnx.load(SRC)
    graph = model.graph
    kept = [n for n in graph.node if n.output[0] not in {"_pre_pad206", "output"}]
    kept.append(helper.make_node("Pad", ["out_b", "_p206_pads", "false_b"], ["output"], name="pad_bool_output"))

    del graph.node[:]
    graph.node.extend(kept)
    del graph.output[:]
    graph.output.extend([helper.make_tensor_value_info("output", TensorProto.BOOL, [1, 10, 30, 30])])
    graph.initializer.extend([init("false_b", np.array(False, dtype=np.bool_))])
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
