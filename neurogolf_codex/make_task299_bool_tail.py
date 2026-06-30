from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now/task299.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task299_bool_tail.onnx")


def main():
    model = onnx.load(BASE)
    for node in model.graph.node:
        if node.op_type == "Concat" and node.output and node.output[0] == "y6":
            del node.input[:]
            node.input.extend(["mask0_b", "zero_b", "mask2_b", "zero_b", "mask4_b", "zero_b", "zero_b", "zero_b", "mask8_b", "zero_b"])
        if node.op_type == "Pad" and node.output and node.output[0] == "output":
            del node.input[:]
            node.input.extend(["y6", "pad_to_30", "false_bool"])
    keep = []
    for node in model.graph.node:
        if node.output and node.output[0] in {"ch0", "ch2", "ch4", "ch8"}:
            continue
        keep.append(node)
    del model.graph.node[:]
    model.graph.node.extend(keep)
    names = {i.name for i in model.graph.initializer}
    if "zero_b" not in names:
        model.graph.initializer.append(numpy_helper.from_array(np.zeros((1, 1, 6, 6), dtype=bool), name="zero_b"))
    if "false_bool" not in names:
        model.graph.initializer.append(numpy_helper.from_array(np.array(False, dtype=bool), name="false_bool"))
    for out in model.graph.output:
        if out.name == "output":
            out.type.tensor_type.elem_type = TensorProto.BOOL
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
