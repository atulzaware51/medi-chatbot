
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix
)

# Example claim-level labels:
# 1 = Supported by reference evidence
# 0 = Unsupported by reference evidence

y_true = [1, 1, 0, 1, 0, 1, 0, 1]
y_pred = [1, 1, 1, 1, 0, 0, 0, 1]

accuracy = accuracy_score(y_true, y_pred)
precision = precision_score(y_true, y_pred, zero_division=0)
recall = recall_score(y_true, y_pred, zero_division=0)
f1 = f1_score(y_true, y_pred, zero_division=0)

tn, fp, fn, tp = confusion_matrix(
    y_true, y_pred, labels=[0, 1]
).ravel()

print("========== MEDIBOT EVALUATION ==========")
print(f"Accuracy  : {accuracy:.4f} ({accuracy * 100:.2f}%)")
print(f"Precision : {precision:.4f} ({precision * 100:.2f}%)")
print(f"Recall    : {recall:.4f} ({recall * 100:.2f}%)")
print(f"F1 Score  : {f1:.4f} ({f1 * 100:.2f}%)")

print("\nConfusion Matrix:")
print(f"TP: {tp}, FP: {fp}")
print(f"FN: {fn}, TN: {tn}")

# Claim-level hallucination calculation
total_claims = len(y_true)
unsupported_claims = sum(
    1 for actual, predicted in zip(y_true, y_pred)
    if predicted == 1 and actual == 0
)

hallucination_rate = (
    unsupported_claims / total_claims * 100
    if total_claims else 0
)

print(f"\nUnsupported claim rate: {hallucination_rate:.2f}%")
