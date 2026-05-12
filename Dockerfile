#build stage
FROM python:3.11-slim AS builder

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y gcc python3-dev

WORKDIR /app

# Copy requirements files first to leverage Docker cache
COPY requirements.txt .
COPY requirements-dev.txt .

# Install dependencies into a specific directory
RUN pip install --prefix=/install -r requirements.txt \ 
	&& pip install --prefix=/install -r requirements-dev.txt

# Stage 2: Final runtime stage
FROM python:3.11-slim

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application source code
COPY /app ./app

# Create a non-root user for security and set permissions
RUN useradd -m myuser && chown -R myuser /app 
USER myuser

# Set the command to run the FastAPI app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Document the port that the container listens on
EXPOSE 8000

