# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP=dbviewer.py
ENV FLASK_ENV=production 
# Note: FLASK_SECRET_KEY, DBVIEWER_ADMIN_TOKEN, REDIS_URL should be set at runtime (e.g., via docker-compose)

# Install system dependencies
# unixodbc-dev is for pyodbc.
# Other packages like freetds-dev and tdsodbc are often needed for SQL Server via odbc.
# For MS Access (.mdb/.accdb) on Linux, specific drivers like mdbtools or libmdbodbc might be needed.
# This setup prioritizes SQLite and general ODBC capabilities.
RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc-dev \
    odbc-mdbtools \
    # Consider adding other drivers if specific DBs like MS Access are critical in Docker on Linux
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy custom ODBC configuration
COPY odbcinst.ini /etc/odbcinst.ini

# Copy application code
COPY . .

# Create a non-root user and group
RUN addgroup --system app && adduser --system --group app

# Create uploads directory and app.log, and set permissions
# These will be owned by the 'app' user.
# If using host-mounted volumes, ensure host directory permissions align or manage permissions at runtime.
RUN mkdir -p /app/uploads && \
    touch /app/app.log && \
    chown -R app:app /app/uploads /app/app.log

# Switch to the non-root user
USER app

# Expose port Gunicorn will run on
EXPOSE 8000

# Run the application using Gunicorn
# The number of workers can be adjusted based on the server's resources.
# Gunicorn will look for the 'app' Flask instance in 'dbviewer.py' (FLASK_APP).
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:8000", "dbviewer:app"]
