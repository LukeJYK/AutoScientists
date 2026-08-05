---
name: Hybrid Molecular Features + Transformer for Caco-2 Permeability
team: caco_local2_analyst3
---

# Proposal: Hybrid Molecular Features + Transformer for Caco-2 Permeability Prediction

## Mechanism
This proposal combines molecular fingerprints (ECFP) with a transformer-based architecture to leverage both structural information and sequence modeling capabilities. The approach extracts molecular fingerprints as input features and processes them through a transformer encoder to predict permeability values.

## Diff
```python
# Add hybrid model to train.py
import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoModel

class HybridModel(nn.Module):
    def __init__(self, fingerprint_dim=2048, hidden_dim=256, num_heads=8, num_layers=4):
        super(HybridModel, self).__init__()
        self.fingerprint_encoder = nn.Linear(fingerprint_dim, hidden_dim)
        self.transformer = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d_model=hidden_dim, nhead=num_heads),
            num_layers=num_layers
        )
        self.output_layer = nn.Linear(hidden_dim, 1)
    
    def forward(self, fingerprint_features, mask=None):
        encoded = torch.relu(self.fingerprint_encoder(fingerprint_features))
        encoded = encoded.unsqueeze(0)  # Add sequence dimension
        transformed = self.transformer(encoded, src_key_padding_mask=mask)
        # Take the first token output
        output = self.output_layer(transformed[0])
        return output

# Replace the existing model with HybridModel
model = HybridModel()
```

## Paper Reference
This approach builds upon:
- Ribeiro et al. (2020) - "Strategies for Pre-training Graph Neural Networks"
- Vaswani et al. (2017) - "Attention is All You Need"

## Expected Impact
The hybrid approach combines the structural encoding power of molecular fingerprints with the contextual modeling capabilities of transformers. This could potentially capture both local molecular features and global structural patterns more effectively than either approach alone.

## Team
caco_local2_analyst3

## Axis
model_architecture
direction
increase
value
hybrid_transformer_gnn
current_value
traditional_ml
```