from pathlib import Path
import argparse

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


CONFIG = {
    "task226": {
        "src": "/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now/task226.onnx",
        "pad_input": "out10",
        "pad_output": "output",
        "pads": "pad_to_30_channelpad",
    },
    "task030": {
        "src": "/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now/task030.onnx",
        "pad_input": "out5",
        "pad_output": "output",
        "pads": "pads30",
    },
    "task229": {
        "src": "/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now/task229.onnx",
        "pad_input": "combined_c",
        "pad_output": "output",
        "pads": "pads_c",
    },
    "task052": {
        "src": "/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_now/task052.onnx",
        "pad_input": "combined",
        "pad_output": "output",
        "pads": "pads_c",
    },
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    args = parser.parse_args()
    cfg = CONFIG[args.task]
    model = onnx.load(cfg["src"])
    graph = model.graph
    kept = [n for n in graph.node if n.output[0] != cfg["pad_output"]]
    cast_name = f"{cfg['pad_input']}_u8"
    kept.extend(
        [
            helper.make_node("Cast", [cfg["pad_input"]], [cast_name], name="prepad_to_u8", to=TensorProto.UINT8),
            helper.make_node("Pad", [cast_name, cfg["pads"], "zero_u8"], [cfg["pad_output"]], name="pad_u8_output", mode="constant"),
        ]
    )
    del graph.node[:]
    graph.node.extend(kept)
    del graph.output[:]
    graph.output.extend([helper.make_tensor_value_info(cfg["pad_output"], TensorProto.UINT8, [1, 10, 30, 30])])
    graph.initializer.extend([init("zero_u8", np.array(0, dtype=np.uint8))])
    onnx.checker.check_model(model)
    out = Path(f"/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/{args.task}.onnx")
    out.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, out)
    print(out)


if __name__ == "__main__":
    main()
