# Dockerfile for pygwire proxy (functional testing)
FROM python:3.11-slim

WORKDIR /app

# Copy package files for installation
COPY pyproject.toml ./
COPY src/ ./src/
COPY README.md ./
COPY tests/infrastructure/proxy/proxy.py ./

# Install pygwire and its dependencies
RUN pip install --no-cache-dir -e .

# Expose proxy port
EXPOSE 5433

# Run proxy in strict mode
CMD ["python", "proxy.py", \
     "--proxy-port", "5433", \
     "--server-host", "postgres", \
     "--server-port", "5432", \
     "--strict"]
