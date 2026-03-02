# Installation

## Requirements

- Python 3.11 or later
- No runtime dependencies

## Install from PyPI

=== "pip"

    ```bash
    pip install pygwire
    ```

=== "uv"

    ```bash
    uv add pygwire
    ```

=== "poetry"

    ```bash
    poetry add pygwire
    ```

## Install from source

```bash
git clone https://github.com/DHUKK/pygwire.git
cd pygwire
pip install .
```

## Verify installation

```python
import pygwire
from pygwire.messages import Query

query = Query(query_string="SELECT 1")
print(query.to_wire())  # Raw wire protocol bytes
```
