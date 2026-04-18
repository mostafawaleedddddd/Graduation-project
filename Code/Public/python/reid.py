import torch
import torch.nn as nn
import torchvision.models as models
import torchvision.transforms as T
import numpy as np
from scipy.spatial.distance import cosine

class ReID:
    def __init__(self):
        backbone = models.mobilenet_v3_small(weights="IMAGENET1K_V1")
        self.model = nn.Sequential(*list(backbone.children())[:-1])
        self.model.eval()

        self.transform = T.Compose([
            T.ToPILImage(),
            T.Resize((128, 64)),
            T.ToTensor(),
            T.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])

        self.memory = {}  

    def extract(self, frame, box):
        x1, y1, x2, y2 = map(int, box)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        img = self.transform(crop).unsqueeze(0)
        with torch.no_grad():
            emb = self.model(img).flatten().cpu().numpy()

        norm = np.linalg.norm(emb)
        return emb / norm if norm > 0 else None

    def remember(self, track_id, embedding):
        self.memory[track_id] = embedding

    def match(self, embedding, threshold=0.35):
        best_id = None
        best_score = threshold

        for tid, emb in self.memory.items():
            dist = cosine(embedding, emb)
            if dist < best_score:
                best_score = dist
                best_id = tid

        return best_id
