from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now/task030.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task030_bool_tail.onnx")


def main():
    model = onnx.load(BASE)
    new_nodes = []
    for node in model.graph.node:
        if node.op_type == "Concat" and node.output and node.output[0] == "out5":
            new_nodes.extend(
                [
                    helper.make_node("Cast", ["out0"], ["out0_b"], name="out0_bool", to=TensorProto.BOOL),
                    helper.make_node("Cast", ["outp1"], ["outp1_b"], name="outp1_bool", to=TensorProto.BOOL),
                    helper.make_node("Cast", ["outp2"], ["outp2_b"], name="outp2_bool", to=TensorProto.BOOL),
                    helper.make_node("Cast", ["outp4"], ["outp4_b"], name="outp4_bool", to=TensorProto.BOOL),
                ]
            )
            del node.input[:]
            node.input.extend(["out0_b", "outp1_b", "outp2_b", "zero_b", "outp4_b"])
        if node.op_type == "Pad" and node.output and node.output[0] == "output":
            del node.input[:]
            node.input.extend(["out5", "pads30", "false_bool"])
        new_nodes.append(node)
    del model.graph.node[:]
    model.graph.node.extend(new_nodes)
    names = {i.name for i in model.graph.initializer}
    if "zero_b" not in names:
        model.graph.initializer.append(numpy_helper.from_array(np.zeros((1, 1, 10, 10), dtype=bool), name="zero_b"))
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
