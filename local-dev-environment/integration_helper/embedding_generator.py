"""This script generates a mock embedding vector for testing purposes.
It creates a list of 1024 random floating-point numbers between 0 and 1.
This vector can be used in tests or as a placeholder for actual embeddings.
It is not intended for production use."""

import numpy as np

# A list of 1024 random floating-point numbers between 0 and 1.
mock_embedding = (np.trunc(np.random.rand(1024) * 100) / 100).tolist()

print(mock_embedding)  # noqa: T201
