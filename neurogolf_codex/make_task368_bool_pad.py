from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


SRC = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_fresh/task368.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task368.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    model = onnx.load(SRC)
    graph = model.graph
    kept = [n for n in graph.node if n.output[0] not in {"out10", "output"}]
    kept.extend(
        [
            helper.make_node("Cast", ["ob"], ["out10_u8"], name="out_bool_to_u8", to=TensorProto.UINT8),
            helper.make_node("Pad", ["out10_u8", "pad_out", "zero_u8"], ["output"], name="pad_u8_output", mode="constant"),
        ]
    )

    del graph.node[:]
    graph.node.extend(kept)
    del graph.output[:]
    graph.output.extend([helper.make_tensor_value_info("output", TensorProto.UINT8, [1, 10, 30, 30])])
    graph.initializer.extend([init("zero_u8", np.array(0, dtype=np.uint8))])
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
