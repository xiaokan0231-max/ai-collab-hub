from pathlib import Path

import onnx
from onnx import helper


BASE = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now/task353.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task353_bg_simplify.onnx")


def main():
    model = onnx.load(BASE)
    keep = []
    for node in model.graph.node:
        if node.output and node.output[0] in {"ch_0", "ch_0_b", "ch_3_b", "xor_03_b", "ch_0_out_b"}:
            continue
        keep.append(node)
        if node.output and node.output[0] == "ch_3_out_b":
            keep.append(helper.make_node("Or", ["ch_3_out_b", "ch_4_b"], ["non_bg_b"], name="non_bg"))
            keep.append(helper.make_node("Not", ["non_bg_b"], ["ch_0_out_b"], name="bg_out"))
    del model.graph.node[:]
    model.graph.node.extend(keep)
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
