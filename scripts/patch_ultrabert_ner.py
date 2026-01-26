"""
Patch familyos_ultrabert pytorch_inference.py to add confidence threshold to NER.

This fixes the issue where UltraBERT NER tags random common words as entities
because argmax is used without any confidence threshold check.

Root cause: _postprocess_token_classification uses torch.argmax which picks
the label with highest probability even if that probability is only 12%.

Fix: Add softmax + confidence threshold check. Tokens below threshold are
treated as O (outside entity) regardless of the argmax prediction.
"""

import sys

PYTORCH_INFERENCE_PATH = (
    "/usr/local/lib/python3.10/dist-packages/familyos_ultrabert/pytorch_inference.py"
)

# Read the file
with open(PYTORCH_INFERENCE_PATH, "r") as f:
    content = f.read()

# The old function signature and body to replace
OLD_CODE = '''def _postprocess_token_classification(
    logits: torch.Tensor, tokens: List[str], schema: LabelSchema
) -> Dict[str, Any]:
    """Extract entities from token classification logits.

    Handles ModernBERT tokenization where:
    - Tokens starting with 'Ġ' indicate word boundaries (space before token)
    - Tokens starting with '##' indicate BERT-style subword continuations
    - Tokens without these prefixes (after the first real token) are subword continuations

    This ensures subword tokens like ['Em', 'ma'] are merged into 'Emma' even if
    the model incorrectly predicts B-* labels for continuation tokens.
    """
    pred_ids = torch.argmax(logits, dim=-1)[0].cpu().numpy()
    pred_labels = [schema.id2label[int(i)] for i in pred_ids]'''

# The new version with confidence threshold
NEW_CODE = '''def _postprocess_token_classification(
    logits: torch.Tensor, tokens: List[str], schema: LabelSchema,
    min_entity_confidence: float = 0.5
) -> Dict[str, Any]:
    """Extract entities from token classification logits.

    Handles ModernBERT tokenization where:
    - Tokens starting with 'Ġ' indicate word boundaries (space before token)
    - Tokens starting with '##' indicate BERT-style subword continuations
    - Tokens without these prefixes (after the first real token) are subword continuations

    This ensures subword tokens like ['Em', 'ma'] are merged into 'Emma' even if
    the model incorrectly predicts B-* labels for continuation tokens.

    Args:
        logits: Raw model logits of shape (batch, seq_len, num_labels)
        tokens: List of tokens from the tokenizer
        schema: Label schema with id2label mapping
        min_entity_confidence: Minimum probability to accept an entity prediction.
            Tokens below this threshold are treated as O (outside any entity).
            Default 0.5 filters out low-confidence garbage predictions.
    """
    # Get probabilities and apply confidence threshold
    probs = torch.softmax(logits, dim=-1)[0]  # (seq_len, num_labels)
    max_probs, pred_ids_tensor = probs.max(dim=-1)
    max_probs_np = max_probs.cpu().numpy()
    pred_ids = pred_ids_tensor.cpu().numpy()

    # Convert to labels, applying confidence threshold
    pred_labels = []
    for pred_id, prob in zip(pred_ids, max_probs_np):
        if prob < min_entity_confidence:
            # Below threshold - treat as O regardless of predicted label
            pred_labels.append("O")
        else:
            pred_labels.append(schema.id2label[int(pred_id)])'''

if OLD_CODE in content:
    content = content.replace(OLD_CODE, NEW_CODE)

    # Also update entity dict to include confidence
    OLD_ENTITY = """current_entity = {
                "text": clean_token,
                "label": label[2:],
                "start_token": i,
                "end_token": i,
            }"""

    NEW_ENTITY = """current_entity = {
                "text": clean_token,
                "label": label[2:],
                "start_token": i,
                "end_token": i,
                "confidence": float(max_probs_np[i]),
            }"""

    content = content.replace(OLD_ENTITY, NEW_ENTITY)

    # Write back
    with open(PYTORCH_INFERENCE_PATH, "w") as f:
        f.write(content)

    print("Successfully patched pytorch_inference.py!")
    print("- Added min_entity_confidence parameter (default 0.5)")
    print("- Entity predictions now include confidence score")
    print("- Low-confidence predictions are now treated as O (no entity)")
else:
    print("ERROR: Could not find the expected function signature.")
    print("The file may have already been patched or the format changed.")
    sys.exit(1)
