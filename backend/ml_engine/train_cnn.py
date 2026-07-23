"""
Train a lightweight CNN (MobileNetV3-Small, transfer learning) to classify
genuine vs. tampered certificate images.

Why MobileNetV3-Small: it's small enough to run on CPU (matters for your
Render free-tier deploy — you're already CPU-bound with the SRCNN in
ai_engine.py), and transfer learning means you only need to fit a small
head + fine-tune the last block, which works with a few hundred images.

Usage:
    python train_cnn.py --data ./dataset --epochs 12 --out cnn_tamper_model.pt

Requires: torch, torchvision  (pip install torch torchvision --break-system-packages)
"""

import argparse
import os
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split
from torchvision import datasets, transforms, models


def build_model() -> nn.Module:
    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
    # freeze backbone, only train the classifier head + last block
    for param in model.features.parameters():
        param.requires_grad = False
    for param in model.features[-3:].parameters():
        param.requires_grad = True

    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, 2)  # genuine=0, tampered=1
    return model


def main(data_dir: str, epochs: int, batch_size: int, out_path: str):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Device:", device)

    train_tf = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(0.0),  # certs aren't flip-invariant, keep off
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    full_ds = datasets.ImageFolder(data_dir, transform=train_tf)
    print("Classes:", full_ds.classes)  # expect ['genuine', 'tampered'] -> [0, 1]

    n_val = max(1, int(0.15 * len(full_ds)))
    n_train = len(full_ds) - n_val
    train_ds, val_ds = random_split(full_ds, [n_train, n_val])

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size)

    model = build_model().to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(
        [p for p in model.parameters() if p.requires_grad], lr=1e-4
    )

    best_acc = 0.0
    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        for imgs, labels in train_loader:
            imgs, labels = imgs.to(device), labels.to(device)
            optimizer.zero_grad()
            out = model(imgs)
            loss = criterion(out, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * imgs.size(0)

        model.eval()
        correct, total = 0, 0
        with torch.no_grad():
            for imgs, labels in val_loader:
                imgs, labels = imgs.to(device), labels.to(device)
                preds = model(imgs).argmax(dim=1)
                correct += (preds == labels).sum().item()
                total += labels.size(0)
        val_acc = correct / max(total, 1)
        print(f"Epoch {epoch+1}/{epochs}  loss={running_loss/len(train_ds):.4f}  val_acc={val_acc:.3f}")

        if val_acc >= best_acc:
            best_acc = val_acc
            torch.save({
                "state_dict": model.state_dict(),
                "classes": full_ds.classes,
            }, out_path)

    print(f"Best val_acc={best_acc:.3f}  saved to {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="Dataset folder with genuine/ and tampered/ subfolders")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--out", default="cnn_tamper_model.pt")
    args = ap.parse_args()
    main(args.data, args.epochs, args.batch_size, args.out)
