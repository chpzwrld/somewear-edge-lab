# Course environment for running the Somewear Edge Lab outside Codespaces.
# Usually started with ./launch.sh (or: docker compose run --rm course)
FROM python:3.11-slim

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        iproute2 iputils-ping netcat-openbsd tcpdump socat procps sudo diffutils less nano \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /course
CMD ["bash", "-c", "python3 course.py; exec bash"]
