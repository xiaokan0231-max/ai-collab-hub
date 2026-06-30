from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


SRC = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/current_artifacts_fresh/task161.onnx")
OUT = Path("/Users/kanxiao/IdeaProjects/ai-collab-hub/neurogolf_codex/candidates/task161.onnx")


def init(name, arr):
    return numpy_helper.from_array(np.asarray(arr), name=name)


def main():
    model = onnx.load(SRC)
    graph = model.graph

    # Keep the proven rule extraction, but replace the 10-channel selector tail:
    # old tail: target_b -> Where(... [1,10,H,W] selector) -> Mul(... [1,10,H,W])
    # new tail: line mask -> uint8 color grid -> Equal directly as graph output.
    kept = [n for n in graph.node if n.output[0] not in {"selector_oh", "output"}]
    produced = {out for n in kept for out in n.output}
    if "target_b" not in produced or "rare_idx_i64" not in produced or "in_grid_u8" not in produced:
        raise SystemExit("unexpected source graph shape")

    kept.extend(
        [
            helper.make_node("Cast", ["rare_idx_i64"], ["rare_u8_1"], name="rare_idx_to_u8", to=TensorProto.UINT8),
            helper.make_node("Reshape", ["rare_u8_1", "shape_1111"], ["rare_u8"], name="rare_color_scalar"),
            helper.make_node("Where", ["target_b", "rare_u8", "zero_u8"], ["grid_raw"], name="paint_lines"),
            helper.make_node("Cast", ["in_grid_u8"], ["valid_b"], name="valid_cell_bool", to=TensorProto.BOOL),
            helper.make_node("Where", ["valid_b", "grid_raw", "sentinel_u8"], ["grid_u8"], name="mask_padding"),
            helper.make_node("Equal", ["grid_u8", "colors_u8"], ["output"], name="equal_as_output"),
        ]
    )

    del graph.node[:]
    graph.node.extend(kept)
    del graph.output[:]
    graph.output.extend([helper.make_tensor_value_info("output", TensorProto.BOOL, [1, 10, 30, 30])])
    graph.initializer.extend(
        [
            init("shape_1111", np.array([1, 1, 1, 1], dtype=np.int64)),
            init("zero_u8", np.array([0], dtype=np.uint8).reshape(1, 1, 1, 1)),
            init("sentinel_u8", np.array([255], dtype=np.uint8).reshape(1, 1, 1, 1)),
            init("colors_u8", np.arange(10, dtype=np.uint8).reshape(1, 10, 1, 1)),
        ]
    )
    onnx.checker.check_model(model)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
