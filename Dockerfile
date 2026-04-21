FROM python:3.13-slim

# Install system dependencies (Git is required for our Runner)
RUN apt-get update && apt-get install -y git make && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory
WORKDIR /app

# Copy dependency files first (for better caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-install-project

# Copy the source code
COPY src ./src

# Expose the NiceGUI port
EXPOSE 8080

# Run the application
CMD ["uv", "run", "python", "-m", "mijen.main"]
